"""Минимальный сервер для проверки связки.

Задача этого кода — не работать красиво, а ответить на один вопрос: держатся
ли вместе FastAPI, uvicorn в фоновом потоке, pywebview и PyInstaller. Всё,
что здесь есть, — один эндпоинт и один поток событий.
"""

from __future__ import annotations

import asyncio
import socket
import sys
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def free_port() -> int:
    """Занимает свободный порт и сразу отпускает его.

    Фиксированный номер брать нельзя: два запущенных экземпляра подрались бы
    за него, а на чужой машине он может быть занят чем угодно.
    """
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def static_dir() -> Path | None:
    """Папка собранного фронта — рядом с кодом или внутри бандла PyInstaller."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    else:
        base = Path(__file__).resolve().parent.parent
    candidate = base / "frontend" / "dist"
    return candidate if candidate.is_dir() else None


def create_app() -> FastAPI:
    app = FastAPI(title="VoxDuo spike", docs_url="/api/docs")

    @app.get("/api/ping")
    async def ping() -> dict[str, str]:
        """Проверка, что HTTP вообще ходит."""
        return {"status": "ok", "frozen": str(bool(getattr(sys, "frozen", False)))}

    @app.websocket("/ws")
    async def ws(websocket: WebSocket) -> None:
        """Поток событий: то, ради чего берётся FastAPI.

        В настоящем приложении отсюда пойдёт уровень микрофона пятнадцать раз
        в секунду. Здесь — просто счётчик с тем же темпом.
        """
        await websocket.accept()
        tick = 0
        try:
            while True:
                tick += 1
                await websocket.send_json({"type": "tick", "value": tick})
                await asyncio.sleep(1 / 15)
        except WebSocketDisconnect:
            return

    static = static_dir()
    if static is not None:
        app.mount("/assets", StaticFiles(directory=static / "assets"), name="assets")

        @app.get("/")
        async def index() -> FileResponse:
            return FileResponse(static / "index.html")

    return app
