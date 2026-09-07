"""Режим «голос → текст».

Долгие операции — загрузка модели и распознавание — уходят в фоновые потоки,
а результат возвращается в интерфейс через after(). Первая версия проекта
грузила модель прямо в конструкторе окна, и приложение висело на несколько
секунд при каждом запуске.

Подтверждение копирования сделано тремя сигналами сразу: всплывающая плашка,
кнопка на полторы секунды меняет вид, поле подсвечивается. Одного мало —
человек не замечает и жмёт повторно.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from typing import Any

import customtkinter as ctk
import pyperclip

from ..config import AppConfig
from ..history import SttEntry
from ..stt import recorder as rec
from ..stt.engine import LANGUAGE_CHOICES, MODEL_CHOICES, ModelLoadError, SttEngine
from . import theme
from ._bridge import post
from .history_view import HistoryList

log = logging.getLogger(__name__)

COPIED_FEEDBACK_MS = 1500


class SttView(ctk.CTkFrame):
    """Экран записи и распознавания."""

    def __init__(
        self,
        master: Any,
        config: AppConfig,
        engine: SttEngine,
        history: Any,
        on_status: Callable[[str], None],
        on_toast: Callable[[str, str], None],
        on_config_changed: Callable[[], None],
        **kwargs: Any,
    ) -> None:
        super().__init__(master, fg_color="transparent", **kwargs)
        self._config = config
        self._engine = engine
        self._history = history
        self._status = on_status
        self._toast = on_toast
        self._config_changed = on_config_changed

        self._recorder = rec.Recorder(config.stt.input_device)
        self._level_job: str | None = None
        self._busy = False
        self._copy_reset_job: str | None = None

        self._build()
        self.refresh_history()

    # --- построение ---

    def _build(self) -> None:
        controls = ctk.CTkFrame(self, fg_color="transparent")
        controls.pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkLabel(controls, text="Модель:", text_color=theme.color("muted")).pack(
            side="left", padx=(0, 6)
        )
        self._model_menu = ctk.CTkOptionMenu(
            controls,
            values=list(MODEL_CHOICES.values()),
            width=250,
            command=self._on_model_changed,
        )
        self._model_menu.set(MODEL_CHOICES.get(self._config.stt.model, ""))
        self._model_menu.pack(side="left", padx=(0, 14))

        ctk.CTkLabel(controls, text="Язык:", text_color=theme.color("muted")).pack(
            side="left", padx=(0, 6)
        )
        self._language_menu = ctk.CTkOptionMenu(
            controls,
            values=list(LANGUAGE_CHOICES.values()),
            width=160,
            command=self._on_language_changed,
        )
        self._language_menu.set(LANGUAGE_CHOICES.get(self._config.stt.language, ""))
        self._language_menu.pack(side="left")

        # --- запись ---
        record_row = ctk.CTkFrame(self, fg_color="transparent")
        record_row.pack(fill="x", padx=12, pady=(6, 4))

        self._record_button = ctk.CTkButton(
            record_row,
            text="🎤  Записать",
            height=46,
            width=190,
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color=theme.color("record"),
            hover_color=theme.color("record_hover"),
            command=self._toggle_recording,
        )
        self._record_button.pack(side="left")

        self._level = ctk.CTkProgressBar(record_row, height=10)
        self._level.set(0)
        self._level.pack(side="left", fill="x", expand=True, padx=(14, 0))

        # --- текст ---
        self._text = ctk.CTkTextbox(
            self,
            font=ctk.CTkFont(size=14),
            wrap="word",
            height=180,
        )
        self._text.pack(fill="both", expand=True, padx=12, pady=(8, 6))

        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=12, pady=(0, 6))

        self._copy_button = ctk.CTkButton(
            buttons,
            text="📋  Копировать",
            width=170,
            height=34,
            command=self.copy_text,
        )
        self._copy_button.pack(side="left")

        ctk.CTkButton(
            buttons,
            text="Очистить",
            width=110,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._clear_text,
        ).pack(side="left", padx=8)

        # --- история ---
        self._history_view = HistoryList(
            self,
            title="История расшифровок",
            on_pick=self._use_entry,
            actions=[("⧉", "Скопировать", self._copy_entry)],
            empty_text="Пока ничего не распознано",
        )
        self._history_view.pack(fill="x", padx=8, pady=(0, 8))

    # --- запись ---

    def _toggle_recording(self) -> None:
        if self._busy:
            return
        if self._recorder.is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        self._recorder = rec.Recorder(self._config.stt.input_device)
        try:
            self._recorder.start()
        except Exception as exc:
            self._status(f"Не удалось открыть микрофон: {exc}")
            self._toast("Микрофон недоступен", "danger")
            return

        self._record_button.configure(
            text="⏹  Стоп",
            fg_color=theme.color("recording"),
            hover_color=theme.color("recording_hover"),
        )
        self._status("Идёт запись…")
        self._poll_level()

    def _poll_level(self) -> None:
        """Обновляет индикатор громкости, пока идёт запись."""
        if not self._recorder.is_recording:
            self._level.set(0)
            self._level_job = None
            return
        self._level.set(self._recorder.level)
        self._level_job = self.after(60, self._poll_level)

    def _stop_recording(self) -> None:
        audio = self._recorder.stop()
        self._level.set(0)
        self._record_button.configure(
            text="🎤  Записать",
            fg_color=theme.color("record"),
            hover_color=theme.color("record_hover"),
        )

        if audio.size == 0:
            self._status("Микрофон не дал звука — проверьте устройство")
            self._toast("Запись пуста", "warning")
            return

        seconds = rec.duration_seconds(audio)
        if seconds < 0.3:
            self._status("Слишком короткая запись")
            self._toast("Слишком коротко", "warning")
            return

        self._set_busy(True)
        threading.Thread(
            target=self._transcribe_worker, args=(audio,), name="transcribe", daemon=True
        ).start()

    def _transcribe_worker(self, audio: Any) -> None:
        """Фоновая часть: распознавание. В интерфейс возвращаемся через after."""
        try:
            result = self._engine.transcribe(
                audio,
                self._config.replacements,
                on_status=lambda text: post(self, self._status, text),
            )
        except ModelLoadError as exc:
            post(self, self._on_error, f"Не удалось загрузить модель: {exc}")
            return
        except Exception as exc:
            log.exception("Ошибка распознавания")
            post(self, self._on_error, f"Ошибка распознавания: {exc}")
            return
        post(self, self._on_transcribed, result)

    def _on_transcribed(self, result: Any) -> None:
        self._set_busy(False)

        if not result.text:
            self._status("Речь не распознана — возможно, была тишина")
            self._toast("Ничего не распознано", "warning")
            return

        self._text.delete("1.0", "end")
        self._text.insert("1.0", result.text)

        self._history.add_stt(
            SttEntry(
                text=result.text,
                audio_seconds=result.audio_seconds,
                elapsed_seconds=result.elapsed_seconds,
                model=result.model,
                language=result.language,
            )
        )
        self.refresh_history()

        self._status(
            f"Готово за {result.elapsed_seconds:.1f} с "
            f"({result.speed_ratio:.1f}× от реального времени, {result.device})"
        )

    def _on_error(self, message: str) -> None:
        self._set_busy(False)
        self._status(message)
        self._toast("Ошибка распознавания", "danger")

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        self._record_button.configure(state="disabled" if busy else "normal")
        if busy:
            self._status("Распознавание…")

    # --- текст ---

    def copy_text(self) -> None:
        """Копирует расшифровку и показывает это тремя способами сразу."""
        text = self._text.get("1.0", "end").strip()
        if not text:
            self._toast("Нечего копировать", "warning")
            return

        try:
            pyperclip.copy(text)
        except Exception as exc:
            log.error("Не удалось скопировать в буфер: %s", exc)
            self._status(f"Буфер обмена недоступен: {exc}")
            self._toast("Не удалось скопировать", "danger")
            return

        self._toast("✓ Скопировано в буфер", "success")
        self._flash_copy_button()
        self._flash_text_field()
        self._status("Текст скопирован в буфер обмена")

    def _flash_copy_button(self) -> None:
        if self._copy_reset_job is not None:
            self.after_cancel(self._copy_reset_job)
        self._copy_button.configure(
            text="✓  Скопировано",
            fg_color=theme.color("success"),
            hover_color=theme.color("success"),
        )
        self._copy_reset_job = self.after(COPIED_FEEDBACK_MS, self._reset_copy_button)

    def _reset_copy_button(self) -> None:
        self._copy_reset_job = None
        default = ctk.ThemeManager.theme["CTkButton"]
        self._copy_button.configure(
            text="📋  Копировать",
            fg_color=default["fg_color"],
            hover_color=default["hover_color"],
        )

    def _flash_text_field(self) -> None:
        original = self._text.cget("fg_color")
        self._text.configure(fg_color=theme.color("highlight"))
        self.after(COPIED_FEEDBACK_MS, lambda: self._text.configure(fg_color=original))

    def _clear_text(self) -> None:
        self._text.delete("1.0", "end")
        self._status("Поле очищено")

    def set_text(self, text: str) -> None:
        self._text.delete("1.0", "end")
        self._text.insert("1.0", text)

    # --- история ---

    def refresh_history(self) -> None:
        self._history_view.render(self._history.stt)

    def _use_entry(self, entry: SttEntry) -> None:
        self.set_text(entry.text)
        self._status("Запись из истории подставлена в поле")

    def _copy_entry(self, entry: SttEntry) -> None:
        try:
            pyperclip.copy(entry.text)
        except Exception as exc:
            self._toast("Не удалось скопировать", "danger")
            self._status(f"Буфер обмена недоступен: {exc}")
            return
        self._toast("✓ Скопировано в буфер", "success")
        self._status("Запись из истории скопирована")

    # --- настройки ---

    def _on_model_changed(self, label: str) -> None:
        for key, text in MODEL_CHOICES.items():
            if text == label:
                if key != self._config.stt.model:
                    self._config.stt.model = key
                    self._engine.update_config(self._config.stt)
                    self._config_changed()
                    self._status(f"Модель переключена на {key}")
                break

    def _on_language_changed(self, label: str) -> None:
        for key, text in LANGUAGE_CHOICES.items():
            if text == label:
                self._config.stt.language = key
                self._engine.update_config(self._config.stt)
                self._config_changed()
                break

    def sync_from_config(self) -> None:
        """Подтягивает значения после изменения настроек в другом окне."""
        self._model_menu.set(MODEL_CHOICES.get(self._config.stt.model, ""))
        self._language_menu.set(LANGUAGE_CHOICES.get(self._config.stt.language, ""))
        self._recorder = rec.Recorder(self._config.stt.input_device)

    def shutdown(self) -> None:
        if self._level_job is not None:
            try:
                self.after_cancel(self._level_job)
            except Exception:
                log.debug("Опрос уровня уже остановлен")
        if self._recorder.is_recording:
            self._recorder.cancel()
