"""Сводка об окружении — для troubleshooting и баг-репортов.

Вызывается через `python -m voxduo --check`. Первое, что стоит попросить
у человека, если приложение ведёт себя странно: здесь видно и версии,
и доступность видеокарты, и какие движки синтеза удалось подключить.
"""

from __future__ import annotations

import platform
import sys
from importlib import metadata

from . import __version__, cuda_setup, paths

# Пакеты, версии которых имеют значение при разборе проблем
_TRACKED = (
    "faster-whisper",
    "ctranslate2",
    "onnxruntime",
    "customtkinter",
    "edge-tts",
    "piper-tts",
    "torch",
    "sounddevice",
    "soundfile",
    "numpy",
    "nvidia-cublas-cu12",
    "nvidia-cudnn-cu12",
)


def _version_of(package: str) -> str:
    try:
        return metadata.version(package)
    except metadata.PackageNotFoundError:
        return "не установлен"


def collect() -> list[tuple[str, str]]:
    """Собирает пары «что» → «значение»."""
    device, compute_type = cuda_setup.resolve_device("auto")
    rows: list[tuple[str, str]] = [
        ("VoxDuo", __version__),
        ("Python", sys.version.split()[0]),
        ("Интерпретатор", sys.executable),
        ("Система", f"{platform.system()} {platform.release()}"),
        ("Данные приложения", str(paths.data_dir())),
        ("Устройств CUDA", str(cuda_setup.cuda_device_count())),
        ("Выбранное устройство", f"{device} / {compute_type}"),
    ]
    rows.extend((package, _version_of(package)) for package in _TRACKED)

    try:
        import soundfile

        rows.append(("libsndfile", soundfile.__libsndfile_version__))
        rows.append(("MP3 читается", "да" if "MP3" in soundfile.available_formats() else "нет"))
    except Exception as exc:
        rows.append(("soundfile", f"ошибка: {exc}"))

    return rows


def render() -> str:
    rows = collect()
    width = max(len(name) for name, _ in rows)
    lines = [f"{name.ljust(width)}  {value}" for name, value in rows]
    return "\n".join(lines)
