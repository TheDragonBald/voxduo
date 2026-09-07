"""Светлая и тёмная темы.

CustomTkinter переключает свои виджеты сам, от нас нужны только собственные
цвета — акценты кнопок, статусы, подсветка. Каждый задаётся парой
(светлая, тёмная): виджеты принимают кортеж и меняют цвет мгновенно, без
пересоздания окна. Именно поэтому ни один цвет здесь не записан одиночным
значением, даже если на вид он одинаков в обеих темах.
"""

from __future__ import annotations

import logging

import customtkinter as ctk

log = logging.getLogger(__name__)

# Порядок в кортеже — (светлая тема, тёмная тема)
COLORS: dict[str, tuple[str, str]] = {
    # Запись: зелёный в покое, красный во время записи
    "record": ("#2e9e57", "#3ab06a"),
    "record_hover": ("#268a4b", "#45c07a"),
    "recording": ("#d64545", "#e05757"),
    "recording_hover": ("#c03a3a", "#eb6a6a"),
    # Подтверждение копирования
    "success": ("#2e9e57", "#3ab06a"),
    "success_text": ("#1b6b39", "#7ee0a5"),
    # Предупреждения: сработал не тот движок, микрофон молчит
    "warning": ("#b8791a", "#e0a44a"),
    "danger": ("#c03a3a", "#e05757"),
    # Второстепенный текст: время в истории, подписи лицензий
    "muted": ("#6b7280", "#9aa3af"),
    # Подсветка поля после копирования
    "highlight": ("#d7f0e0", "#1f4433"),
    "surface": ("#f2f3f5", "#2b2b2b"),
}

APPEARANCE_LABELS: dict[str, str] = {
    "system": "Как в системе",
    "light": "Светлая",
    "dark": "Тёмная",
}


def color(name: str) -> tuple[str, str]:
    """Пара цветов для виджета."""
    return COLORS[name]


def apply(mode: str) -> None:
    """Устанавливает тему: system, light или dark."""
    if mode not in APPEARANCE_LABELS:
        log.warning("Неизвестная тема %r, используем системную", mode)
        mode = "system"
    ctk.set_appearance_mode(mode)
    ctk.set_default_color_theme("blue")
    log.debug("Тема: %s", mode)


def current_is_dark() -> bool:
    """Тёмная ли тема сейчас — нужно там, где цвет считается вручную."""
    return ctk.get_appearance_mode().lower() == "dark"


def pick(name: str) -> str:
    """Один цвет под текущую тему, когда кортеж передать некуда."""
    light, dark = COLORS[name]
    return dark if current_is_dark() else light


def next_mode(mode: str) -> str:
    """Следующая тема по кругу для кнопки-переключателя."""
    order = ["system", "light", "dark"]
    try:
        return order[(order.index(mode) + 1) % len(order)]
    except ValueError:
        return "system"


def mode_icon(mode: str) -> str:
    """Значок для кнопки переключения темы."""
    return {"system": "🌗", "light": "☀", "dark": "🌙"}.get(mode, "🌗")
