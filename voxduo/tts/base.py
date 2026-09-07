"""Общий интерфейс движков синтеза и цепочка переключения между ними.

Движков три, и они дополняют друг друга: edge-tts звучит живее всех, но
требует сети и периодически отваливается по 403, когда Microsoft обновляет
версию токена; Silero и Piper работают офлайн. Поэтому синтез идёт по
цепочке, а не одним движком, и пользователю честно сообщается, если озвучил
не тот, что был выбран.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

log = logging.getLogger(__name__)


class TtsError(RuntimeError):
    """Общая ошибка синтеза."""


class TtsUnavailable(TtsError):
    """Движок недоступен: нет пакета, нет модели или нет сети."""


class EdgeTokenExpired(TtsError):
    """Microsoft требует более свежую версию Edge — помогает смена версии токена."""


class EdgeClockSkew(TtsError):
    """Системные часы разошлись с сервером настолько, что подпись не принимается."""


@dataclass(frozen=True)
class Voice:
    """Голос в виде, пригодном для списка в интерфейсе."""

    id: str
    label: str
    # Лицензию показываем рядом с голосом: часть голосов запрещена к
    # коммерческому использованию, и пользователь должен это видеть
    license: str = ""
    noncommercial: bool = False

    def __str__(self) -> str:
        if self.license:
            return f"{self.label} — {self.license}"
        return self.label


@runtime_checkable
class TtsEngine(Protocol):
    """Контракт движка синтеза."""

    name: str
    title: str

    def is_available(self) -> bool:
        """Можно ли пользоваться движком прямо сейчас (без обращения к сети)."""
        ...

    def list_voices(self) -> list[Voice]: ...

    def synthesize(self, text: str, voice: str, rate: int, pitch: int, out_path: Path) -> Path:
        """Синтезирует речь в файл и возвращает путь к нему."""
        ...


@dataclass
class SynthesisOutcome:
    """Что получилось: файл, движок и предупреждение, если сработал не тот движок."""

    path: Path
    engine: str
    voice: str
    warning: str | None = None


def synthesize_with_fallback(
    engines: dict[str, TtsEngine],
    order: list[str],
    text: str,
    voices: dict[str, str],
    rate: int,
    pitch: int,
    out_path: Path,
) -> SynthesisOutcome:
    """Пробует движки по порядку, пока один не справится.

    Первым идёт выбранный пользователем, дальше — остальные из order.
    Если сработал не первый, в результате остаётся предупреждение: подмена
    движка не должна происходить молча, голоса звучат по-разному.
    """
    if not text.strip():
        raise TtsError("Нечего озвучивать: текст пуст")

    attempted: list[str] = []
    failures: list[str] = []

    for index, name in enumerate(order):
        engine = engines.get(name)
        if engine is None:
            continue
        attempted.append(name)

        if not engine.is_available():
            failures.append(f"{engine.title}: недоступен")
            log.info("Движок %s недоступен, пробуем следующий", name)
            continue

        voice = voices.get(name) or ""
        try:
            path = engine.synthesize(text, voice, rate, pitch, out_path)
        except TtsError as exc:
            failures.append(f"{engine.title}: {exc}")
            log.warning("Движок %s не справился: %s", name, exc)
            continue
        except Exception as exc:
            failures.append(f"{engine.title}: {exc}")
            log.exception("Неожиданная ошибка движка %s", name)
            continue

        warning = None
        if index > 0:
            # Первым в order всегда идёт выбранный пользователем движок, но в
            # реестре его может не быть вовсе — например, пакет не установлен
            preferred = engines.get(order[0])
            preferred_title = preferred.title if preferred is not None else order[0]
            warning = f"{preferred_title} недоступен, озвучено через {engine.title}"
        return SynthesisOutcome(path=path, engine=name, voice=voice, warning=warning)

    if not attempted:
        raise TtsUnavailable("Ни один движок синтеза не подключён")
    raise TtsUnavailable("Ни один движок не смог озвучить текст. " + "; ".join(failures))


def build_order(preferred: str, fallback_order: list[str]) -> list[str]:
    """Порядок перебора: сначала выбранный движок, затем остальные."""
    order = [preferred] if preferred else []
    order.extend(name for name in fallback_order if name != preferred)
    return order
