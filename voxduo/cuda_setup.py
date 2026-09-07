"""Подключение CUDA-библиотек из pip-пакетов NVIDIA и выбор устройства.

Проблема, которую решает этот модуль. CTranslate2 (движок faster-whisper)
загружает cuBLAS и cuDNN как обычные DLL. Пакеты nvidia-cublas-cu12 и
nvidia-cudnn-cu12 кладут их внутрь site-packages, куда Windows не заглядывает
при поиске библиотек. Итог — знаменитое «Could not locate cudnn_ops64_9.dll»
при исправно работающей видеокарте.

Одного os.add_dll_directory здесь мало, и это выясняется не сразу.
Он действует только на загрузку через механизм Python, а CTranslate2 тянет
cublas64_12.dll изнутри своей нативной библиотеки обычным LoadLibrary,
который смотрит на PATH процесса. Поэтому каталоги добавляются и туда, и
туда: без add_dll_directory не найдётся cuDNN, без PATH — cuBLAS.

Сделать это надо ДО первого импорта faster_whisper, поэтому
register_cuda_dlls() вызывается на старте приложения, а не внутри модуля
распознавания.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import sys
from pathlib import Path

log = logging.getLogger(__name__)

# Подпапки внутри пакета nvidia перебираем целиком: помимо cudnn и cublas
# ctranslate2 может потянуть, например, cuda_nvrtc, а состав пакетов
# меняется от версии к версии.

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


def _prepend_to_path(directory: Path) -> None:
    """Добавляет каталог в начало PATH процесса.

    Нужно именно это, а не только add_dll_directory: нативный загрузчик
    внутри CTranslate2 ищет зависимости по PATH.
    """
    current = os.environ.get("PATH", "")
    entry = str(directory)
    if entry in current.split(os.pathsep):
        return
    os.environ["PATH"] = entry + os.pathsep + current


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
        if not root.is_dir():
            continue
        for package in sorted(root.iterdir()):
            if not package.is_dir():
                continue
            # У разных версий пакетов библиотеки лежат либо в bin, либо в bin/x64
            for candidate in (package / "bin", package / "bin" / "x64"):
                if not candidate.is_dir() or not any(candidate.glob("*.dll")):
                    continue
                try:
                    os.add_dll_directory(str(candidate))
                except OSError as exc:
                    log.warning("Не удалось добавить путь к DLL %s: %s", candidate, exc)
                    continue
                _prepend_to_path(candidate)
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
