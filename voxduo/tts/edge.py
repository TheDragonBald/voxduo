"""Синтез через нейроголоса Microsoft Edge.

Звучит живее остальных доступных вариантов и не требует ничего скачивать,
но у движка есть особенность, ради которой написана половина этого модуля.

Каждый запрос подписывается заголовком Sec-MS-GEC: это SHA256 от времени,
округлённого до пятиминутного интервала, и общего секрета. Рядом уходит
Sec-MS-GEC-Version, собранный из версии Chromium. Отсюда две совершенно
разные причины ответа 403, и лечатся они по-разному:

* Разошлись часы. edge-tts умеет это чинить сам: читает заголовок Date из
  ответа и повторяет запрос со сдвигом. Если не помогло — часы Windows
  сбиты всерьёз, и это чинит пользователь.
* Устарела версия Edge. Microsoft начала требовать более свежий Chromium.
  Лечится обновлением пакета либо подменой версии — для этого есть
  set_chromium_version().

Важная деталь реализации: SEC_MS_GEC_VERSION импортируется в communicate.py
и voices.py по значению, поэтому подменять константу нужно именно в этих
модулях. Патч самого edge_tts.constants ни на что не влияет.
"""

from __future__ import annotations

import logging
from pathlib import Path

from .base import EdgeClockSkew, EdgeTokenExpired, TtsError, TtsUnavailable, Voice

log = logging.getLogger(__name__)

# Расхождение часов, начиная с которого виним время, а не версию токена.
# Подпись живёт пятиминутными интервалами, поэтому берём порог чуть больше.
CLOCK_SKEW_THRESHOLD_SECONDS = 360

VOICES: tuple[Voice, ...] = (
    Voice("ru-RU-SvetlanaNeural", "Светлана — женский, русский"),
    Voice("ru-RU-DmitryNeural", "Дмитрий — мужской, русский"),
    Voice("en-US-AriaNeural", "Aria — женский, английский"),
    Voice("en-US-GuyNeural", "Guy — мужской, английский"),
)


def set_chromium_version(version: str) -> bool:
    """Подменяет версию Edge в подписи запросов.

    Пустая строка возвращает версию, зашитую в пакет. Возвращает True, если
    подмена удалась. Нужна, чтобы починить 403 сразу, не дожидаясь релиза
    edge-tts: актуальную версию видно в браузере на edge://settings/help.
    """
    try:
        from edge_tts import communicate, constants, voices
    except ImportError:
        return False

    target = version.strip() or constants.CHROMIUM_FULL_VERSION
    value = f"1-{target}"

    patched = False
    for module in (communicate, voices):
        if hasattr(module, "SEC_MS_GEC_VERSION"):
            module.SEC_MS_GEC_VERSION = value
            patched = True

    if patched:
        log.info("Версия Edge для подписи запросов: %s", target)
    else:
        log.warning("Не удалось подменить версию Edge: структура пакета изменилась")
    return patched


def _clock_skew_seconds() -> float:
    """Насколько часы разошлись с сервером по данным самого edge-tts."""
    try:
        from edge_tts.drm import DRM

        return abs(float(getattr(DRM, "clock_skew_seconds", 0.0)))
    except Exception:
        return 0.0


def _classify(exc: Exception) -> TtsError:
    """Превращает исключение в понятную причину.

    Ради этого разбора всё и затевалось: «ошибка синтеза» не подсказывает,
    что делать, а «проверьте часы» или «обновите версию Edge» — подсказывает.
    """
    status = getattr(exc, "status", None) or getattr(exc, "code", None)
    text = str(exc)

    if status == 403 or "403" in text:
        skew = _clock_skew_seconds()
        if skew > CLOCK_SKEW_THRESHOLD_SECONDS:
            return EdgeClockSkew(
                f"часы разошлись с сервером на {skew:.0f} с — проверьте время Windows"
            )
        return EdgeTokenExpired(
            "Microsoft требует более свежую версию Edge. "
            "Укажите актуальную версию в настройках или обновите edge-tts"
        )

    lowered = text.lower()
    if any(
        marker in lowered for marker in ("getaddrinfo", "network", "connect", "temporary failure")
    ):
        return TtsUnavailable("нет подключения к интернету")
    if "timeout" in lowered or "timed out" in lowered:
        return TtsUnavailable("сервер не ответил вовремя")
    return TtsError(text or exc.__class__.__name__)


def _percent(value: int) -> str:
    """Формат, который ждёт edge-tts: со знаком и процентом."""
    return f"{value:+d}%"


def _hertz(value: int) -> str:
    return f"{value:+d}Hz"


class EdgeTts:
    """Движок синтеза на нейроголосах Edge."""

    name = "edge"
    title = "edge-tts"

    def __init__(self, chromium_version: str = "") -> None:
        self._chromium_version = chromium_version
        self._version_applied = False

    def is_available(self) -> bool:
        """Пакет на месте. Наличие сети проверяется уже при синтезе."""
        try:
            import edge_tts  # noqa: F401
        except ImportError:
            return False
        return True

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def _apply_version(self) -> None:
        if self._version_applied or not self._chromium_version:
            return
        set_chromium_version(self._chromium_version)
        self._version_applied = True

    def synthesize(self, text: str, voice: str, rate: int, pitch: int, out_path: Path) -> Path:
        try:
            import edge_tts
        except ImportError as exc:
            raise TtsUnavailable("пакет edge-tts не установлен") from exc

        self._apply_version()

        voice_id = voice or VOICES[0].id
        out_path = out_path.with_suffix(".mp3")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            edge_tts.Communicate(
                text,
                voice_id,
                rate=_percent(rate),
                pitch=_hertz(pitch),
            ).save_sync(str(out_path))
        except Exception as exc:
            raise _classify(exc) from exc

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise TtsError("сервис вернул пустой ответ")

        log.info("edge-tts: озвучено голосом %s, %d байт", voice_id, out_path.stat().st_size)
        return out_path
