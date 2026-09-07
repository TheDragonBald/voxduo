"""Окно настроек.

Здесь живут вещи, которые меняют редко, но без которых иногда не обойтись:
микрофон, подсказка для Whisper, словарь замен и версия Edge — та самая,
подмена которой чинит 403, когда Microsoft обновит требования к клиенту.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from ..config import AppConfig
from ..stt import recorder as rec
from . import theme

log = logging.getLogger(__name__)

DEFAULT_DEVICE_LABEL = "Устройство по умолчанию"


class SettingsWindow(ctk.CTkToplevel):
    """Отдельное окно настроек."""

    def __init__(self, master: Any, config: AppConfig, on_save: Callable[[], None]) -> None:
        super().__init__(master)
        self._config = config
        self._on_save = on_save

        self.title("VoxDuo — настройки")
        self.geometry("640x620")
        self.minsize(560, 520)
        self.transient(master)

        self._build()
        # Поднимаем после отрисовки: иначе окно иногда уходит за главное
        self.after(120, self._raise)

    def _raise(self) -> None:
        try:
            self.lift()
            self.focus_force()
            self.grab_set()
        except Exception:
            log.debug("Не удалось поднять окно настроек")

    def _build(self) -> None:
        container = ctk.CTkScrollableFrame(self, fg_color="transparent")
        container.pack(fill="both", expand=True, padx=14, pady=(14, 0))

        # --- микрофон ---
        _section(container, "Микрофон")
        devices = rec.list_input_devices()
        self._device_labels = [DEFAULT_DEVICE_LABEL] + [d.name for d in devices]
        self._device_menu = ctk.CTkOptionMenu(container, values=self._device_labels, width=420)
        self._device_menu.set(self._config.stt.input_device or DEFAULT_DEVICE_LABEL)
        self._device_menu.pack(anchor="w", pady=(0, 4))
        _hint(
            container,
            f"Найдено устройств: {len(devices)}. "
            "Сохраняется имя, а не номер — новая гарнитура не собьёт выбор.",
        )

        # --- подсказка Whisper ---
        _section(container, "Подсказка для распознавания")
        _hint(
            container,
            "Задаёт стиль расшифровки. Главный рычаг против транслитерации: "
            "перечислите здесь термины так, как хотите их видеть в тексте.",
        )
        self._prompt = ctk.CTkTextbox(container, height=90, wrap="word")
        self._prompt.insert("1.0", self._config.stt.initial_prompt)
        self._prompt.pack(fill="x", pady=(2, 4))

        # --- словарь замен ---
        _section(container, "Словарь замен")
        _hint(
            container,
            "По строке на замену, в виде «что» = «на что». "
            "Применяется после распознавания, целыми словами.",
        )
        self._replacements = ctk.CTkTextbox(container, height=140, wrap="none")
        self._replacements.insert("1.0", _format_replacements(self._config.replacements))
        self._replacements.pack(fill="x", pady=(2, 4))

        # --- edge-tts ---
        _section(container, "Версия Edge для edge-tts")
        _hint(
            container,
            "Если синтез перестал работать с ошибкой 403, укажите здесь текущую "
            "версию браузера — её видно на странице edge://settings/help. "
            "Пусто — использовать версию из пакета.",
        )
        self._chromium = ctk.CTkEntry(container, placeholder_text="например, 143.0.3650.75")
        if self._config.tts.edge_chromium_version:
            self._chromium.insert(0, self._config.tts.edge_chromium_version)
        self._chromium.pack(fill="x", pady=(2, 4))

        # --- логи ---
        _section(container, "Диагностика")
        ctk.CTkButton(
            container, text="Открыть папку с логами", width=220, command=self._open_logs
        ).pack(anchor="w", pady=(0, 10))

        # --- кнопки ---
        buttons = ctk.CTkFrame(self, fg_color="transparent")
        buttons.pack(fill="x", padx=14, pady=12)

        ctk.CTkButton(buttons, text="Сохранить", width=140, command=self._save).pack(side="right")
        ctk.CTkButton(
            buttons,
            text="Отмена",
            width=110,
            fg_color="transparent",
            border_width=1,
            text_color=("gray20", "gray85"),
            command=self._close,
        ).pack(side="right", padx=8)

    def _open_logs(self) -> None:
        import os
        import subprocess

        from .. import paths

        directory = paths.logs_dir()
        directory.mkdir(parents=True, exist_ok=True)
        try:
            if hasattr(os, "startfile"):
                os.startfile(str(directory))  # noqa: S606
            else:
                subprocess.Popen(["xdg-open", str(directory)])
        except Exception as exc:
            log.error("Не удалось открыть папку с логами: %s", exc)

    def _save(self) -> None:
        device = self._device_menu.get()
        self._config.stt.input_device = None if device == DEFAULT_DEVICE_LABEL else device
        self._config.stt.initial_prompt = self._prompt.get("1.0", "end").strip()
        self._config.replacements = _parse_replacements(self._replacements.get("1.0", "end"))
        self._config.tts.edge_chromium_version = self._chromium.get().strip()

        self._on_save()
        self._close()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            log.debug("Захват окна уже снят")
        self.destroy()


def _section(master: Any, title: str) -> None:
    ctk.CTkLabel(master, text=title, font=ctk.CTkFont(size=13, weight="bold"), anchor="w").pack(
        fill="x", pady=(12, 2)
    )


def _hint(master: Any, text: str) -> None:
    ctk.CTkLabel(
        master,
        text=text,
        font=ctk.CTkFont(size=11),
        text_color=theme.color("muted"),
        anchor="w",
        justify="left",
        wraplength=560,
    ).pack(fill="x", pady=(0, 4))


def _format_replacements(replacements: dict[str, str]) -> str:
    return "\n".join(f"{key} = {value}" for key, value in sorted(replacements.items()))


def _parse_replacements(text: str) -> dict[str, str]:
    """Разбирает строки вида «что = на что», молча пропуская мусор."""
    result: dict[str, str] = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if not separator:
            continue
        key, value = key.strip(), value.strip()
        if key and value:
            result[key] = value
    return result
