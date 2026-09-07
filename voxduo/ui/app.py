"""Главное окно.

Собирает всё вместе и владеет общим состоянием: настройками, историей,
движками. Оба режима живут в одном окне и переключаются сегментированной
кнопкой в шапке — так их видно сразу, в отличие от вкладок, которые легко
принять за декорацию.

Движки синтеза создаются сразу все три, но ничего не грузят до первого
обращения: конструкторы у них пустые, модели подтягиваются лениво.
"""

from __future__ import annotations

import logging
from typing import Any

import customtkinter as ctk

from .. import __version__
from .. import config as config_module
from ..history import History
from ..stt.engine import SttEngine
from ..tts.edge import EdgeTts
from ..tts.piper import PiperTts
from ..tts.silero import SileroTts
from . import theme
from .settings_view import SettingsWindow
from .stt_view import SttView
from .toast import Toast
from .tts_view import TtsView

log = logging.getLogger(__name__)

MODE_STT = "🎤  Голос → Текст"
MODE_TTS = "🔊  Текст → Голос"

WINDOW_MIN_WIDTH = 720
WINDOW_MIN_HEIGHT = 640


class VoxDuoApp(ctk.CTk):
    """Окно приложения."""

    def __init__(self) -> None:
        super().__init__()

        self._config = config_module.load()
        theme.apply(self._config.theme)

        self.title(f"VoxDuo {__version__}")
        self.geometry("820x760")
        self.minsize(WINDOW_MIN_WIDTH, WINDOW_MIN_HEIGHT)

        self._history = History()
        self._history.load()

        self._stt_engine = SttEngine(self._config.stt)
        self._tts_engines: dict[str, Any] = {
            "edge": EdgeTts(self._config.tts.edge_chromium_version),
            "silero": SileroTts(),
            "piper": PiperTts(),
        }

        self._toast = Toast(self)
        self._settings_window: SettingsWindow | None = None

        self._build_header()
        self._build_status()
        self._build_views()

        self._switch_mode(MODE_STT if self._config.mode == "stt" else MODE_TTS)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        log.info("Окно готово, режим %s", self._config.mode)

    # --- построение ---

    def _build_header(self) -> None:
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=14, pady=(12, 4))

        ctk.CTkLabel(header, text="VoxDuo", font=ctk.CTkFont(size=20, weight="bold")).pack(
            side="left", padx=(2, 18)
        )

        self._mode_switch = ctk.CTkSegmentedButton(
            header,
            values=[MODE_STT, MODE_TTS],
            command=self._switch_mode,
            font=ctk.CTkFont(size=13),
            height=34,
        )
        self._mode_switch.pack(side="left")

        ctk.CTkButton(
            header,
            text="⚙",
            width=38,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._open_settings,
        ).pack(side="right", padx=(6, 0))

        self._theme_button = ctk.CTkButton(
            header,
            text=theme.mode_icon(self._config.theme),
            width=38,
            height=34,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._toggle_theme,
        )
        self._theme_button.pack(side="right")

    def _build_status(self) -> None:
        self._status_label = ctk.CTkLabel(
            self,
            text="Готов к работе",
            anchor="w",
            font=ctk.CTkFont(size=12),
            text_color=theme.color("muted"),
        )
        self._status_label.pack(side="bottom", fill="x", padx=16, pady=(0, 8))

    def _build_views(self) -> None:
        self._container = ctk.CTkFrame(self, fg_color="transparent")
        self._container.pack(fill="both", expand=True)

        self._stt_view = SttView(
            self._container,
            config=self._config,
            engine=self._stt_engine,
            history=self._history,
            on_status=self.set_status,
            on_toast=self.show_toast,
            on_config_changed=self._save_config,
        )
        self._tts_view = TtsView(
            self._container,
            config=self._config,
            engines=self._tts_engines,
            history=self._history,
            on_status=self.set_status,
            on_toast=self.show_toast,
            on_config_changed=self._save_config,
        )

    # --- режимы ---

    def _switch_mode(self, value: str) -> None:
        self._stt_view.pack_forget()
        self._tts_view.pack_forget()

        if value == MODE_STT:
            self._stt_view.pack(fill="both", expand=True)
            self._config.mode = "stt"
        else:
            self._tts_view.pack(fill="both", expand=True)
            self._config.mode = "tts"

        self._mode_switch.set(value)
        self._save_config()

    # --- тема ---

    def _toggle_theme(self) -> None:
        self._config.theme = theme.next_mode(self._config.theme)
        theme.apply(self._config.theme)
        self._theme_button.configure(text=theme.mode_icon(self._config.theme))
        self.set_status(f"Тема: {theme.APPEARANCE_LABELS[self._config.theme].lower()}")
        self._save_config()

    # --- настройки ---

    def _open_settings(self) -> None:
        if self._settings_window is not None and self._settings_window.winfo_exists():
            self._settings_window.focus()
            return
        self._settings_window = SettingsWindow(self, self._config, self._on_settings_saved)

    def _on_settings_saved(self) -> None:
        self._save_config()
        self._stt_engine.update_config(self._config.stt)
        self._tts_engines["edge"] = EdgeTts(self._config.tts.edge_chromium_version)
        self._stt_view.sync_from_config()
        self._tts_view.sync_from_config()
        self.set_status("Настройки сохранены")
        self.show_toast("✓ Настройки сохранены", "success")

    def _save_config(self) -> None:
        config_module.save(self._config)

    # --- общие сервисы для экранов ---

    def set_status(self, text: str) -> None:
        self._status_label.configure(text=text)

    def show_toast(self, text: str, kind: str = "success") -> None:
        self._toast.show(text, kind)

    # --- закрытие ---

    def _on_close(self) -> None:
        log.info("Закрытие приложения")
        try:
            self._stt_view.shutdown()
            self._tts_view.shutdown()
            self._toast.destroy()
            self._save_config()
            self._history.save()
        except Exception:
            log.exception("Ошибка при закрытии")
        self.destroy()


def run() -> int:
    """Точка входа интерфейса."""
    app = VoxDuoApp()
    app.mainloop()
    return 0
