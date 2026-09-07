"""Подключение CUDA-библиотек из pip-пакетов NVIDIA и выбор устройства.

Проблема, которую решает этот модуль. CTranslate2 (движок faster-whisper)
загружает cuBLAS и cuDNN как обычные DLL. Пакеты nvidia-cublas-cu12 и
nvidia-cudnn-cu12 кладут их внутрь site-packages, куда Windows не заглядывает
при поиске библиотек. Итог — знаменитое «Could not locate cudnn_ops64_9.dll»
при исправно работающей видеокарте.

Начиная с Python 3.8 путь к DLL нужно регистрировать явно через
os.add_dll_directory, и сделать это надо ДО первого импорта faster_whisper.
Поэтому register_cuda_dlls() вызывается на старте приложения, а не внутри
модуля распознавания.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Подпапки пакета nvidia, где лежат нужные библиотеки
_CUDA_PACKAGES = ("cudnn", "cublas")

_registered = False


def _nvidia_roots() -> list[Path]:
    """Каталоги пакета nvidia в текущем окружении."""
    try:
        spec = importlib.util.find_spec("nvidia")
    except (ImportError, ValueError):
        return []
    if spec is None or not spec.submodule_search_locations:
        return []
    return [Path(p) for p in spec.submodule_search_locations]


def register_cuda_dlls() -> list[Path]:
    """Регистрирует каталоги с CUDA-библиотеками. Возвращает добавленные пути.

    Идемпотентна: повторные вызовы ничего не делают. На не-Windows и при
    отсутствии пакетов NVIDIA молча возвращает пустой список — это штатная
    ситуация для работы на процессоре.
    """
    global _registered
    if _registered or sys.platform != "win32":
        return []

    added: list[Path] = []
    for root in _nvidia_roots():
        for package in _CUDA_PACKAGES:
            # У разных версий пакетов библиотеки лежат либо в bin, либо в bin/x64
            for candidate in (root / package / "bin", root / package / "bin" / "x64"):
                if not candidate.is_dir():
                    continue
                try:
                    os.add_dll_directory(str(candidate))
                except OSError as exc:
                    log.warning("Не удалось добавить путь к DLL %s: %s", candidate, exc)
                    continue
                added.append(candidate)
                log.debug("Зарегистрирован путь к CUDA DLL: %s", candidate)

    _registered = True
    if added:
        log.info("Подключено каталогов с CUDA-библиотеками: %d", len(added))
    else:
        log.info("Пакеты CUDA не найдены — работаем на процессоре")
    return added


def cuda_device_count() -> int:
    """Сколько видеокарт видит CTranslate2. Ноль означает работу на CPU."""
    try:
        import ctranslate2
    except ImportError:
        log.debug("ctranslate2 не установлен")
        return 0
    try:
        return int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        # Драйвер есть, но библиотеки не сошлись по версиям — это не повод падать
        log.warning("Не удалось опросить CUDA: %s", exc)
        return 0


def resolve_device(preference: str = "auto") -> tuple[str, str]:
    """Возвращает пару (device, compute_type) для faster-whisper.

    preference: auto | cuda | cpu. При auto видеокарта используется, если есть.
    float16 выбран для GPU как оптимальный для Turing и новее; int8 на CPU —
    единственный практичный вариант по скорости.
    """
    if preference == "cpu":
        return "cpu", "int8"

    register_cuda_dlls()
    count = cuda_device_count()

    if preference == "cuda":
        if count == 0:
            log.warning("Запрошен GPU, но CUDA недоступна — переключаемся на процессор")
            return "cpu", "int8"
        return "cuda", "float16"

    if count > 0:
        log.info("Обнаружено устройств CUDA: %d — используем GPU", count)
        return "cuda", "float16"

    log.info("CUDA недоступна — используем процессор")
    return "cpu", "int8"
