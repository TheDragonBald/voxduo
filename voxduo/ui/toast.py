"""Всплывающее подтверждение поверх окна.

Нужно ради одной конкретной задачи: сделать копирование в буфер заметным.
Раньше о нём сообщала только строка статуса внизу окна — её легко не увидеть,
и человек жал кнопку повторно, не понимая, сработало ли.

Тост — один из трёх сигналов; остальные два (кнопка меняет вид, поле
подсвечивается) живут в самих экранах. Вместе их пропустить трудно.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

from . import theme

log = logging.getLogger(__name__)

SHOW_MS = 1500  # сколько висит на полной непрозрачности
FADE_STEP_MS = 40
FADE_STEPS = 8


class Toast:
    """Плашка, всплывающая внизу окна и растворяющаяся сама.

    Один экземпляр на окно: повторный вызов show() перезапускает показ, а не
    плодит окна поверх друг друга.
    """

    def __init__(self, master: ctk.CTk) -> None:
        self._master = master
        self._window: ctk.CTkToplevel | None = None
        self._label: ctk.CTkLabel | None = None
        self._after_id: str | None = None

    def show(self, text: str, kind: str = "success") -> None:
        """Показывает сообщение. kind: success, warning или danger."""
        self._cancel_pending()

        if self._window is None or not self._window.winfo_exists():
            self._build()

        assert self._window is not None and self._label is not None

        self._label.configure(text=text, text_color=theme.color(_text_color(kind)))
        self._window.configure(fg_color=theme.color("surface"))
        self._window.attributes("-alpha", 1.0)
        self._window.deiconify()
        self._place()
        self._window.lift()

        self._after_id = self._master.after(SHOW_MS, self._start_fade)

    def hide(self) -> None:
        self._cancel_pending()
        if self._window is not None and self._window.winfo_exists():
            self._window.withdraw()

    def destroy(self) -> None:
        self._cancel_pending()
        if self._window is not None and self._window.winfo_exists():
            self._window.destroy()
        self._window = None
        self._label = None

    # --- внутреннее ---

    def _build(self) -> None:
        window = ctk.CTkToplevel(self._master)
        window.overrideredirect(True)  # без рамки и заголовка
        window.attributes("-topmost", True)
        window.withdraw()

        label = ctk.CTkLabel(
            window,
            text="",
            font=ctk.CTkFont(size=13, weight="bold"),
            padx=18,
            pady=10,
        )
        label.pack()

        self._window = window
        self._label = label

    def _place(self) -> None:
        """Ставит плашку по центру внизу родительского окна."""
        window = self._window
        if window is None:
            return

        window.update_idletasks()
        master = self._master
        try:
            master_x = master.winfo_rootx()
            master_y = master.winfo_rooty()
            master_w = master.winfo_width()
            master_h = master.winfo_height()
        except Exception:
            return

        width = window.winfo_reqwidth()
        height = window.winfo_reqheight()
        x = master_x + (master_w - width) // 2
        y = master_y + master_h - height - 24
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _start_fade(self) -> None:
        self._after_id = None
        self._fade(FADE_STEPS)

    def _fade(self, steps_left: int) -> None:
        window = self._window
        if window is None or not window.winfo_exists():
            return
        if steps_left <= 0:
            window.withdraw()
            return
        try:
            window.attributes("-alpha", steps_left / FADE_STEPS)
        except Exception:
            # Окно могли закрыть посреди затухания
            return
        self._after_id = self._master.after(FADE_STEP_MS, self._fade, steps_left - 1)

    def _cancel_pending(self) -> None:
        if self._after_id is not None:
            try:
                self._master.after_cancel(self._after_id)
            except Exception:
                log.debug("Не удалось отменить отложенный показ тоста")
            self._after_id = None


def _text_color(kind: str) -> str:
    return {
        "success": "success_text",
        "warning": "warning",
        "danger": "danger",
    }.get(kind, "success_text")
