"""Точка входа: python -m voxduo [--debug]

Порядок инициализации здесь важен и не случаен:

1. Разбор аргументов — чтобы знать, включать ли подробное логирование.
2. Настройка логов — до всего остального, иначе ранние ошибки некуда писать.
3. Регистрация CUDA-библиотек — обязательно ДО импорта faster_whisper,
   поэтому модули распознавания импортируются только внутри main().
"""

from __future__ import annotations

import argparse
import contextlib
import logging
import sys

from . import __version__, cuda_setup, logging_setup, paths


def _force_utf8_console() -> None:
    """Заставляет консоль печатать кириллицу читаемо.

    Windows отдаёт stdout в кодировке cp866, и русские сообщения выводятся
    кракозябрами. Переключаем потоки на UTF-8; если консоли нет вовсе
    (запуск через pythonw), просто ничего не делаем.
    """
    for stream in (sys.stdout, sys.stderr):
        if stream is None:
            continue
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is None:
            continue
        with contextlib.suppress(ValueError, OSError):
            reconfigure(encoding="utf-8", errors="replace")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="voxduo",
        description="VoxDuo — распознавание и синтез речи на русском языке",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="подробные логи; в этом режиме в лог попадают и сами тексты",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="показать сводку об окружении и выйти (версии, видеокарта, пути)",
    )
    parser.add_argument("--version", action="version", version=f"VoxDuo {__version__}")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    _force_utf8_console()
    args = parse_args(argv)

    paths.ensure_dirs()
    log_path = logging_setup.setup(debug=args.debug)
    log = logging.getLogger(__name__)

    # До импорта faster_whisper: иначе Windows не найдёт cuDNN и cuBLAS
    cuda_setup.register_cuda_dlls()

    log.info("Данные приложения: %s", paths.data_dir())
    log.info("Файл журнала: %s", log_path)

    if args.check:
        from .diagnostics import render

        print(render())
        return 0

    # Интерфейс появится на следующем этапе
    from .ui.app import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
