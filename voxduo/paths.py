"""Пути к пользовательским данным.

Всё, что приложение создаёт во время работы — настройки, история, логи,
скачанные модели — живёт в %LOCALAPPDATA%/VoxDuo, а не рядом с кодом.
Так собранный .exe и запуск из исходников делят одни и те же данные,
а сама папка проекта остаётся чистой.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from . import __app_name__


def data_dir() -> Path:
    """Корневая папка пользовательских данных."""
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA")
        if base:
            return Path(base) / __app_name__
        # На случай экзотической конфигурации без LOCALAPPDATA
        return Path.home() / "AppData" / "Local" / __app_name__
    # Не основная платформа, но пусть работает предсказуемо
    base = os.environ.get("XDG_DATA_HOME")
    root = Path(base) if base else Path.home() / ".local" / "share"
    return root / __app_name__


def config_file() -> Path:
    return data_dir() / "config.json"


def history_file() -> Path:
    return data_dir() / "history.json"


def audio_dir() -> Path:
    """Аудиофайлы истории синтеза — чтобы переслушивать без пересинтеза."""
    return data_dir() / "audio"


def models_dir() -> Path:
    """Кэш моделей Whisper, Silero и Piper."""
    return data_dir() / "models"


def logs_dir() -> Path:
    return data_dir() / "logs"


def ensure_dirs() -> None:
    """Создаёт все рабочие папки. Вызывается один раз при старте."""
    for path in (data_dir(), audio_dir(), models_dir(), logs_dir()):
        path.mkdir(parents=True, exist_ok=True)
