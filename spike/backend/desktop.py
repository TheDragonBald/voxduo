"""Окно приложения: uvicorn в фоне, pywebview поверх.

Порядок здесь важен и не случаен. Сервер поднимается в потоке-демоне, мы
дожидаемся, пока порт реально начнёт отвечать, и только потом открываем окно —
иначе WebView покажет ошибку соединения раньше, чем сервер успеет встать.
"""

from __future__ import annotations

import contextlib
import json
import multiprocessing
import os
import socket
import sys
import tempfile
import threading
import time
from pathlib import Path

import uvicorn
import webview
from server import create_app, free_port

STARTUP_TIMEOUT_SECONDS = 15


def runtime_file() -> Path:
    """Файл, куда пишется реальный адрес сервера.

    Порт случайный, а знать его нужно: отладке, второму экземпляру,
    автоматической проверке. Читать это из stdout нельзя — собранное
    PyInstaller приложение буферизует вывод в канал до самого закрытия,
    и читающая сторона просто виснет.
    """
    return Path(tempfile.gettempdir()) / "voxduo-spike-runtime.json"


def publish_runtime(port: int) -> None:
    runtime_file().write_text(json.dumps({"port": port, "pid": os.getpid()}), encoding="utf-8")


def clear_runtime() -> None:
    with contextlib.suppress(OSError):
        runtime_file().unlink()


def wait_until_serving(port: int, timeout: float = STARTUP_TIMEOUT_SECONDS) -> bool:
    """Ждёт, пока порт начнёт принимать соединения."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.settimeout(0.2)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                return True
        time.sleep(0.05)
    return False


def force_utf8_console() -> None:
    """Переводит вывод на UTF-8.

    Windows отдаёт stdout в кодировке системы, и русские сообщения либо
    выводятся кракозябрами, либо роняют процесс, который этот вывод читает.
    В основном приложении это уже решено, здесь повторяем то же самое.
    """
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            with contextlib.suppress(ValueError, OSError):
                reconfigure(encoding="utf-8", errors="replace")


def main() -> int:
    force_utf8_console()

    # Без этого uvicorn в собранном приложении плодит копии процесса:
    # PyInstaller запускает exe заново вместо форка
    multiprocessing.freeze_support()

    port = free_port()
    app = create_app()

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, name="uvicorn", daemon=True)
    thread.start()

    if not wait_until_serving(port):
        print(f"Сервер не поднялся на порту {port}", file=sys.stderr)
        return 1

    url = f"http://127.0.0.1:{port}"
    publish_runtime(port)
    print(f"Сервер готов: {url}", flush=True)

    webview.create_window("VoxDuo — проверка связки", url, width=760, height=560)
    webview.start()

    server.should_exit = True
    clear_runtime()
    return 0


if __name__ == "__main__":
    sys.exit(main())
