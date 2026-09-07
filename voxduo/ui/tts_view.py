"""Режим «текст → голос».

Синтез идёт в фоновом потоке через цепочку движков: сначала выбранный, затем
остальные. Если озвучил не тот, что выбран, об этом говорится явно — голоса
звучат по-разному, и молчаливая подмена сбивает с толку.

Список голосов у Silero приходится грузить лениво: он читается из самой
модели, а это несколько десятков мегабайт. Поэтому голоса подтягиваются в
фоне при первом выборе движка, а не при открытии окна.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

import customtkinter as ctk

from ..config import AppConfig
from ..history import TtsEntry
from ..tts import base as tts_base
from ..tts.player import PlaybackError, Player
from . import theme
from ._bridge import post
from .history_view import HistoryList

log = logging.getLogger(__name__)


class TtsView(ctk.CTkFrame):
    """Экран синтеза речи."""

    def __init__(
        self,
        master: Any,
        config: AppConfig,
        engines: dict[str, Any],
        history: Any,
        on_status: Callable[[str], None],
        on_toast: Callable[[str, str], None],
        on_config_changed: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._config = config
        self._engines = engines
        self._history = history
        self._status = on_status
        self._toast = on_toast
        self._config_changed = on_config_changed

        self._player = Player()
        self._busy = False
        self._last_audio: Path | None = None
        self._voice_ids: list[str] = []

        self._build()
        self.refresh_history()
        self._load_voices_async()

    # --- построение ---

    def _build(self) -> None:
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(controls, text="Движок:", text_color=theme.color("muted")).pack(
            side="left", padx=(0, 6)
        )
        self._engine_menu = ctk.CTkOptionMenu(
            controls,
            values=[e.title for e in self._engines.values()],
            width=130,
            command=self._on_engine_changed,
        )
        current = self._engines.get(self._config.tts.engine)
        self._engine_menu.set(current.title if current else "")
        self._engine_menu.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(controls, text="Голос:", text_color=theme.color("muted")).pack(
            side="left", padx=(0, 6)
        )
        self._voice_menu = ctk.CTkOptionMenu(
            controls, values=["загрузка…"], width=280, command=self._on_voice_changed
        )
        self._voice_menu.pack(side="left")

        # --- темп ---
        speed_row = ctk.CTkFrame(self, fg_color="transparent")
        speed_row.pack(fill="x", padx=12, pady=(4, 0))

        ctk.CTkLabel(speed_row, text="Темп:", text_color=theme.color("muted")).pack(
            side="left", padx=(0, 6)
        )
        self._rate_slider = ctk.CTkSlider(
            speed_row, from_=-50, to=50, number_of_steps=20, width=200, command=self._on_rate
        )
        self._rate_slider.set(self._config.tts.rate)
        self._rate_slider.pack(side="left")
        self._rate_label = ctk.CTkLabel(
            speed_row,
            text=_rate_text(self._config.tts.rate),
            width=70,
            text_color=theme.color("muted"),
        )
        self._rate_label.pack(side="left", padx=(8, 0))

        # --- текст ---
        self._text = ctk.CTkTextbox(self, font=ctk.CTkFont(size=14), wrap="word", height=160)
        self._text.pack(fill="both", expand=True, padx=12, pady=(8, 6))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 6))

        self._speak_button = ctk.CTkButton(
            buttons,
            text="🔊  Озвучить",
            width=170,
            height=36,
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self._speak,
        )
        self._speak_button.pack(side="left")

        self._stop_button = ctk.CTkButton(
            buttons,
            text="⏹  Стоп",
            width=100,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._stop_playback,
        )
        self._stop_button.pack(side="left", padx=8)

        ctk.CTkButton(
            buttons,
            text="📋  Из буфера",
            width=140,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._paste_clipboard,
        ).pack(side="left")

        self._save_button = ctk.CTkButton(
            buttons,
            text="💾  Сохранить",
            width=140,
            height=36,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._save_last,
            state="disabled",
        )
        self._save_button.pack(side="right")

        # --- история ---
        self._history_view = HistoryList(
            self,
            title="История озвучек",
            on_pick=self._use_entry,
            actions=[
                ("▶", "Прослушать", self._play_entry),
                ("💾", "Сохранить как…", self._save_entry),
            ],
            empty_text="Пока ничего не озвучено",
        )
        self._history_view.pack(fill="x", padx=8, pady=(0, 8))

    # --- голоса ---

    def _load_voices_async(self) -> None:
        """Silero читает список голосов из модели, поэтому грузим в фоне."""
        threading.Thread(target=self._load_voices_worker, name="voices", daemon=True).start()

    def _load_voices_worker(self) -> None:
        engine = self._engines.get(self._config.tts.engine)
        if engine is None:
            return
        try:
            voices = engine.list_voices()
        except Exception as exc:
            log.warning("Не удалось получить голоса %s: %s", engine.name, exc)
            voices = []
        post(self, self._apply_voices, voices)

    def _apply_voices(self, voices: list[tts_base.Voice]) -> None:
        if not voices:
            self._voice_menu.configure(values=["голоса недоступны"])
            self._voice_menu.set("голоса недоступны")
            self._voice_ids = []
            return

        self._voice_ids = [v.id for v in voices]
        labels = [str(v) for v in voices]
        self._voice_menu.configure(values=labels)

        saved = self._config.tts.voices.get(self._config.tts.engine, "")
        index = self._voice_ids.index(saved) if saved in self._voice_ids else 0
        self._voice_menu.set(labels[index])
        self._config.tts.voices[self._config.tts.engine] = self._voice_ids[index]

        noncommercial = voices[index].noncommercial
        if noncommercial:
            self._status("Внимание: выбранный голос запрещён для коммерческого использования")

    def _on_voice_changed(self, label: str) -> None:
        values = list(self._voice_menu.cget("values"))
        if label not in values:
            return
        voice_id = self._voice_ids[values.index(label)]
        self._config.tts.voices[self._config.tts.engine] = voice_id
        self._config_changed()

    def _on_engine_changed(self, title: str) -> None:
        for name, engine in self._engines.items():
            if engine.title == title:
                self._config.tts.engine = name
                self._config_changed()
                self._voice_menu.configure(values=["загрузка…"])
                self._voice_menu.set("загрузка…")
                self._load_voices_async()
                break

    def _on_rate(self, value: float) -> None:
        self._config.tts.rate = int(value)
        self._rate_label.configure(text=_rate_text(int(value)))

    # --- синтез ---

    def _speak(self) -> None:
        if self._busy:
            return
        text = self._text.get("1.0", "end").strip()
        if not text:
            self._toast("Нечего озвучивать", "warning")
            return

        self._set_busy(True)
        self._status("Синтез речи…")
        threading.Thread(
            target=self._speak_worker, args=(text,), name="synthesis", daemon=True
        ).start()

    def _speak_worker(self, text: str) -> None:
        from .. import paths

        order = tts_base.build_order(self._config.tts.engine, self._config.tts.fallback_order)
        out = paths.data_dir() / "last_synthesis"
        try:
            outcome = tts_base.synthesize_with_fallback(
                self._engines,
                order,
                text,
                self._config.tts.voices,
                self._config.tts.rate,
                self._config.tts.pitch,
                out,
            )
        except tts_base.TtsError as exc:
            post(self, self._on_synthesis_error, str(exc))
            return
        except Exception as exc:
            log.exception("Неожиданная ошибка синтеза")
            post(self, self._on_synthesis_error, str(exc))
            return
        post(self, self._on_synthesised, outcome, text)

    def _on_synthesised(self, outcome: tts_base.SynthesisOutcome, text: str) -> None:
        self._set_busy(False)
        self._last_audio = outcome.path
        self._save_button.configure(state="normal")

        stored = self._history.store_audio(outcome.path)
        self._history.add_tts(
            TtsEntry(text=text, engine=outcome.engine, voice=outcome.voice, audio_name=stored)
        )
        self.refresh_history()

        if outcome.warning:
            self._status(outcome.warning)
            self._toast(outcome.warning, "warning")
        else:
            self._status(f"Озвучено через {self._engines[outcome.engine].title}")

        try:
            self._player.play(outcome.path)
        except PlaybackError as exc:
            self._status(f"Файл готов, но воспроизвести не удалось: {exc}")

    def _on_synthesis_error(self, message: str) -> None:
        self._set_busy(False)
        self._status(f"Не удалось озвучить: {message}")
        self._toast("Синтез не удался", "danger")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._speak_button.configure(state="disabled" if busy else "normal")

    def _stop_playback(self) -> None:
        self._player.stop()
        self._status("Воспроизведение остановлено")

    # --- буфер и сохранение ---

    def _paste_clipboard(self) -> None:
        import pyperclip

        try:
            text = pyperclip.paste()
        except Exception as exc:
            self._status(f"Буфер обмена недоступен: {exc}")
            return
        if not text or not text.strip():
            self._toast("Буфер пуст", "warning")
            return
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text.strip())
        self._status("Текст вставлен из буфера обмена")

    def _save_last(self) -> None:
        if self._last_audio is None:
            return
        self._save_file(self._last_audio)

    def _save_entry(self, entry: TtsEntry) -> None:
        path = entry.audio_path(self._history.audio_dir)
        if path is None:
            self._toast("Файл озвучки не найден", "warning")
            return
        self._save_file(path)

    def _save_file(self, source: Path) -> None:
        from tkinter import filedialog

        target = filedialog.asksaveasfilename(
            title="Сохранить озвучку",
            defaultextension=source.suffix,
            initialfile=f"voxduo{source.suffix}",
            filetypes=[("Аудио", f"*{source.suffix}"), ("Все файлы", "*.*")],
        )
        if not target:
            return
        try:
            import shutil

            shutil.copy2(source, target)
        except OSError as exc:
            self._status(f"Не удалось сохранить: {exc}")
            self._toast("Не удалось сохранить", "danger")
            return
        self._status(f"Сохранено: {target}")
        self._toast("✓ Файл сохранён", "success")

    # --- история ---

    def refresh_history(self) -> None:
        self._history_view.render(self._history.tts)

    def _use_entry(self, entry: TtsEntry) -> None:
        self._text.delete("1.0", "end")
        self._text.insert("1.0", entry.text)
        self._status("Текст из истории подставлен в поле")

    def _play_entry(self, entry: TtsEntry) -> None:
        path = entry.audio_path(self._history.audio_dir)
        if path is None:
            self._toast("Файл озвучки не найден", "warning")
            self.refresh_history()
            return
        try:
            self._player.play(path)
        except PlaybackError as exc:
            self._status(f"Не удалось воспроизвести: {exc}")
            self._toast("Не удалось воспроизвести", "danger")
            return
        self._status("Воспроизводится запись из истории")

    def set_text(self, text: str) -> None:
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)

    def sync_from_config(self) -> None:
        engine = self._engines.get(self._config.tts.engine)
        if engine is not None:
            self._engine_menu.set(engine.title)
        self._rate_slider.set(self._config.tts.rate)
        self._rate_label.configure(text=_rate_text(self._config.tts.rate))
        self._load_voices_async()

    def shutdown(self) -> None:
        self._player.stop()


def _rate_text(value: int) -> str:
    if value == 0:
        return "обычный"
    return f"{value:+d}%"
