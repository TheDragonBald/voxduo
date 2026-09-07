"""Мостик из фоновых потоков в поток интерфейса.

Tkinter требует, чтобы виджеты трогал только главный поток, поэтому результат
любой фоновой работы возвращается через after(). Проблема в том, что окно
могут закрыть раньше, чем поток доделает своё дело: тогда after() падает с
«main thread is not in main loop» либо с TclError об уничтоженном виджете.

Само по себе это безобидно — работать уже некому, — но исключение всплывает в
логе как критическое и выглядит как настоящая поломка. Поэтому все обращения
к интерфейсу из потоков идут через post().
"""

from __future__ import annotations

import logging
import tkinter
from collections.abc import Callable
from typing import Any

log = logging.getLogger(__name__)


def post(widget: Any, callback: Callable[..., Any], *args: Any) -> None:
    """Планирует вызов в потоке интерфейса; молчит, если окна уже нет."""
    try:
        if not widget.winfo_exists():
            return
        widget.after(0, callback, *args)
    except (RuntimeError, tkinter.TclError):
        log.debug("Окно закрыто раньше, чем фоновая задача успела ответить")
