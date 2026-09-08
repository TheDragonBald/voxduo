"""Проверка, что edge-tts ещё отвечает.

Используется еженедельным workflow canary. Ненулевой код возврата означает,
что синтез сломался — обычно из-за того, что Microsoft начала требовать
более свежую версию клиента.

Запуск вручную:
    uv run --frozen --no-sync python scripts/check_edge.py
"""

from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PHRASE = "Проверка связи."
VOICE = "ru-RU-SvetlanaNeural"


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    from edge_tts import constants

    print(f"Версия клиента в пакете: {constants.CHROMIUM_FULL_VERSION}")

    from voxduo.tts.base import EdgeClockSkew, EdgeTokenExpired, TtsError
    from voxduo.tts.edge import EdgeTts

    with tempfile.TemporaryDirectory() as directory:
        started = time.monotonic()
        try:
            path = EdgeTts().synthesize(PHRASE, VOICE, 0, 0, Path(directory) / "probe")
        except EdgeTokenExpired as exc:
            print(f"СЛОМАЛОСЬ: устарела версия клиента — {exc}")
            return 1
        except EdgeClockSkew as exc:
            print(f"СЛОМАЛОСЬ: разошлись часы — {exc}")
            return 1
        except TtsError as exc:
            print(f"СЛОМАЛОСЬ: {exc}")
            return 1

        size = path.stat().st_size
        elapsed = time.monotonic() - started

    if size < 1000:
        print(f"СЛОМАЛОСЬ: ответ подозрительно мал, {size} байт")
        return 1

    print(f"Работает: {size} байт за {elapsed:.1f} с")
    return 0


if __name__ == "__main__":
    sys.exit(main())
