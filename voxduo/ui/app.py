"""Главное окно приложения.

Заглушка до этапа 4: интерфейс собирается там. Сейчас нужна, чтобы точка
входа была рабочей и можно было проверить инициализацию окружения.
"""

from __future__ import annotations

import logging

log = logging.getLogger(__name__)


def run() -> int:
    from ..diagnostics import render

    log.info("Интерфейс ещё не собран — показываем диагностику окружения")
    print("Интерфейс появится на следующем этапе. Пока — сводка об окружении:\n")
    print(render())
    return 0
