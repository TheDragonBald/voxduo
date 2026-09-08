"""Список последних записей.

Один виджет обслуживает оба режима: различаются только кнопки в строке.
Для расшифровок это копирование, для озвучек — воспроизведение и сохранение
файла. Клик по самой строке в обоих случаях возвращает текст в поле ввода.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

import customtkinter as ctk

from . import theme

log = logging.getLogger(__name__)


class HistoryList(ctk.CTkFrame):
    """Список записей истории с кнопками действий."""

    def __init__(
        self,
        master: Any,
        title: str,
        on_pick: Callable[[Any], None],
        actions: list[tuple[str, str, Callable[[Any], None]]] | None = None,
        empty_text: str = "Пока пусто",
        **kwargs: Any,
    ) -> None:
        """actions — список (значок, подсказка, обработчик) для кнопок в строке."""
        super().__init__(master, **kwargs)
        self._on_pick = on_pick
        self._actions = actions or []
        self._empty_text = empty_text
        self._rows: list[ctk.CTkFrame] = []

        self._header = ctk.CTkLabel(
            self,
            text=title,
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=theme.color("muted"),
            anchor="w",
        )
        self._header.pack(fill="x", padx=12, pady=(8, 4))

        self._body = ctk.CTkFrame(self, fg_color="transparent")
        self._body.pack(fill="both", expand=True, padx=6, pady=(0, 8))

        self._title = title

    def render(self, entries: list[Any]) -> None:
        """Перерисовывает список. Записей всего пять, полная перерисовка дешевле diff."""
        for row in self._rows:
            row.destroy()
        self._rows.clear()

        self._header.configure(text=f"{self._title} ({len(entries)})")

        if not entries:
            placeholder = ctk.CTkLabel(
                self._body,
                text=self._empty_text,
                text_color=theme.color("muted"),
                anchor="w",
            )
            placeholder.pack(fill="x", padx=8, pady=6)
            self._rows.append(placeholder)
            return

        for entry in entries:
            self._rows.append(self._build_row(entry))

    def _build_row(self, entry: Any) -> ctk.CTkFrame:
        row = ctk.CTkFrame(self._body, fg_color="transparent")
        row.pack(fill="x", padx=2, pady=1)

        time_label = ctk.CTkLabel(
            row,
            text=entry.time_label,
            width=42,
            anchor="w",
            text_color=theme.color("muted"),
            font=ctk.CTkFont(size=11),
        )
        time_label.pack(side="left", padx=(6, 4))

        preview = ctk.CTkButton(
            row,
            text=entry.preview,
            anchor="w",
            height=26,
            fg_color="transparent",
            hover_color=theme.color("surface"),
            text_color=("gray10", "gray90"),
            command=lambda e=entry: self._on_pick(e),
        )
        preview.pack(side="left", fill="x", expand=True)

        for icon, tooltip, handler in self._actions:
            if not self._action_enabled(icon, entry):
                continue
            button = ctk.CTkButton(
                row,
                text=icon,
                width=32,
                height=26,
                fg_color="transparent",
                hover_color=theme.color("surface"),
                command=lambda e=entry, h=handler: h(e),
            )
            button.pack(side="left", padx=1)
            _attach_tooltip(button, tooltip)

        return row

    def _action_enabled(self, icon: str, entry: Any) -> bool:
        """Кнопку воспроизведения прячем, если файл озвучки пропал."""
        if icon in ("▶", "💾") and hasattr(entry, "audio_name"):
            return bool(entry.audio_name)
        return True


def _attach_tooltip(widget: Any, text: str) -> None:
    """Простейшая подсказка при наведении.

    Своя, потому что в CustomTkinter подсказок нет, а тянуть ради трёх кнопок
    отдельную зависимость не стоит.
    """
    if not text:
        return

    state: dict[str, Any] = {"window": None}

    def show(_event: Any) -> None:
        if state["window"] is not None:
            return
        try:
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() - 28
        except Exception:
            return
        window = ctk.CTkToplevel(widget)
        window.overrideredirect(True)
        window.attributes("-topmost", True)
        label = ctk.CTkLabel(
            window,
            text=text,
            font=ctk.CTkFont(size=11),
            fg_color=theme.color("surface"),
            corner_radius=4,
            padx=8,
            pady=3,
        )
        label.pack()
        window.update_idletasks()
        window.geometry(f"+{x - window.winfo_reqwidth() // 2}+{y}")
        state["window"] = window

    def hide(_event: Any) -> None:
        window = state["window"]
        if window is not None:
            try:
                window.destroy()
            except Exception:
                log.debug("Подсказка уже закрыта")
            state["window"] = None

    widget.bind("<Enter>", show)
    widget.bind("<Leave>", hide)
    widget.bind("<Button-1>", hide, add="+")
