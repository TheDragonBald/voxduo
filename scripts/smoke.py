"""Ручной прогон движков синтеза.

Тестами это не покрыть: нужны сеть, скачивание моделей и живой звук.
Запускать перед релизом и после обновления зависимостей.

    just smoke
    just smoke-play
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from voxduo.tts.base import TtsError  # noqa: E402
from voxduo.tts.edge import EdgeTts  # noqa: E402
from voxduo.tts.piper import PiperTts  # noqa: E402
from voxduo.tts.silero import SileroTts  # noqa: E402

PHRASE = "Проверка синтеза речи. Раз, два, три — всё работает."


def main() -> int:
    parser = argparse.ArgumentParser(description="Прогон всех движков синтеза")
    parser.add_argument("--play", action="store_true", help="проигрывать результат")
    parser.add_argument("--text", default=PHRASE, help="что озвучивать")
    args = parser.parse_args()

    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    out_dir = Path.home() / "AppData" / "Local" / "Temp" / "voxduo_smoke"
    out_dir.mkdir(parents=True, exist_ok=True)

    engines = [EdgeTts(), SileroTts(), PiperTts()]
    failures = 0

    for engine in engines:
        print(f"\n=== {engine.title} ===")
        if not engine.is_available():
            print("  пропущен: движок недоступен (не установлен пакет)")
            continue

        try:
            voices = engine.list_voices()
        except Exception as exc:
            print(f"  список голосов не получен: {exc}")
            failures += 1
            continue

        print(f"  голосов: {len(voices)}")
        for voice in voices[:6]:
            mark = "  (некоммерческий)" if voice.noncommercial else ""
            print(f"    - {voice.id}: {voice}{mark}")

        if not voices:
            print("  нечем озвучивать")
            failures += 1
            continue

        voice_id = voices[0].id
        started = time.monotonic()
        try:
            path = engine.synthesize(args.text, voice_id, 0, 0, out_dir / engine.name)
        except TtsError as exc:
            print(f"  СИНТЕЗ НЕ УДАЛСЯ: {exc}")
            failures += 1
            continue
        except Exception as exc:
            print(f"  НЕОЖИДАННАЯ ОШИБКА: {type(exc).__name__}: {exc}")
            failures += 1
            continue

        elapsed = time.monotonic() - started
        print(f"  синтез: {path.name}, {path.stat().st_size} байт, {elapsed:.1f} с")

        if args.play:
            from voxduo.tts.player import Player

            player = Player()
            player.play(path)
            while player.is_playing:
                time.sleep(0.1)

    print(f"\nИтог: движков с ошибками — {failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
