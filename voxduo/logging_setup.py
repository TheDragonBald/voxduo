"""Логирование в файл с ротацией и перехват необработанных исключений.

Зачем это нужно именно здесь. Приложение запускается ярлыком через pythonw,
без консоли: любой print уходит в никуда. Тяжёлая работа идёт в фоновых
потоках, а исключение в потоке не всплывает в главный — без логов окно просто
замирает на статусе «Обработка…» и причину узнать неоткуда.

О приватности. В обычном режиме содержимое распознанной речи в лог НЕ пишется:
только длина, длительность, модель и время. Тексты попадают в файл лишь под
флагом --debug, включаемым осознанно и на время разбора конкретной проблемы.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys
import threading
from pathlib import Path

from . import __version__, paths

MAX_BYTES = 1_000_000   # ~1 МБ на файл
BACKUP_COUNT = 3        # плюс три архивных — верхняя граница около 4 МБ

# Ставится в setup(); модули спрашивают этот флаг, прежде чем писать в лог
# что-то, что может содержать речь пользователя.
_log_content = False


def content_logging_enabled() -> bool:
    """Разрешено ли писать в лог сами тексты (только в режиме отладки)."""
    return _log_content


def log_file() -> Path:
    return paths.logs_dir() / "voxduo.log"


def setup(debug: bool = False) -> Path:
    """Настраивает корневой логгер и перехват исключений. Возвращает путь к логу."""
    global _log_content
    _log_content = debug

    paths.logs_dir().mkdir(parents=True, exist_ok=True)
    path = log_file()

    level = logging.DEBUG if debug else logging.INFO
    root = logging.getLogger()
    root.setLevel(level)

    # Повторный вызов не должен множить обработчики
    for handler in list(root.handlers):
        root.removeHandler(handler)

    file_handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=MAX_BYTES, backupCount=BACKUP_COUNT, encoding="utf-8"
    )
    file_handler.setFormatter(
        logging.Formatter(
            "%(asctime)s %(levelname)-7s %(threadName)-12s %(name)s: %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    root.addHandler(file_handler)

    # Консоль полезна при запуске из терминала; под pythonw stderr может
    # отсутствовать, поэтому добавляем обработчик только если он есть.
    if sys.stderr is not None:
        console = logging.StreamHandler(sys.stderr)
        console.setFormatter(logging.Formatter("%(levelname)-7s %(name)s: %(message)s"))
        root.addHandler(console)

    _install_excepthooks()

    logging.getLogger(__name__).info(
        "VoxDuo %s запущен, уровень логирования %s", __version__, logging.getLevelName(level)
    )
    return path


def _install_excepthooks() -> None:
    """Направляет необработанные исключения в лог — из главного потока и фоновых."""
    log = logging.getLogger("voxduo.unhandled")

    def handle_exception(exc_type, exc_value, exc_tb):
        # Ctrl+C оставляем стандартному обработчику
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_tb)
            return
        log.critical("Необработанное исключение", exc_info=(exc_type, exc_value, exc_tb))

    def handle_thread_exception(args: threading.ExceptHookArgs) -> None:
        if issubclass(args.exc_type, SystemExit):
            return
        log.critical(
            "Необработанное исключение в потоке %s",
            args.thread.name if args.thread else "?",
            exc_info=(args.exc_type, args.exc_value, args.exc_traceback),
        )

    sys.excepthook = handle_exception
    threading.excepthook = handle_thread_exception
