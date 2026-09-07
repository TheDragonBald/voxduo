"""Синтез через Piper — офлайн, быстрый, на ONNX.

Ценен двумя вещами. Во-первых, работает без сети и без torch: единственная
его зависимость, onnxruntime, уже стоит ради VAD внутри faster-whisper, так
что движок обходится почти бесплатно. Во-вторых, у него есть голоса под CC0,
то есть в общественном достоянии — их можно использовать без оговорок.

Про лицензии голосов: denis и dmitri обучены на датасете CC0, ruslan — на
CC BY-NC-SA (некоммерческое использование), у irina лицензия датасета не
указана вовсе. Поэтому по умолчанию предлагаются первые два, а остальные
показываются с явной пометкой.
"""

from __future__ import annotations

import logging
import wave
from pathlib import Path

from .base import TtsError, TtsUnavailable, Voice

log = logging.getLogger(__name__)

HF_REPO = "rhasspy/piper-voices"

# Ключ — идентификатор голоса, значение — путь внутри репозитория
_VOICE_PATHS: dict[str, str] = {
    "ru_RU-denis-medium": "ru/ru_RU/denis/medium",
    "ru_RU-dmitri-medium": "ru/ru_RU/dmitri/medium",
    "ru_RU-ruslan-medium": "ru/ru_RU/ruslan/medium",
    "ru_RU-irina-medium": "ru/ru_RU/irina/medium",
}

VOICES: tuple[Voice, ...] = (
    Voice("ru_RU-denis-medium", "Денис — мужской", "CC0"),
    Voice("ru_RU-dmitri-medium", "Дмитрий — мужской", "CC0"),
    Voice("ru_RU-ruslan-medium", "Руслан — мужской", "CC BY-NC-SA", noncommercial=True),
    Voice("ru_RU-irina-medium", "Ирина — женский", "лицензия не указана", noncommercial=True),
)

DEFAULT_VOICE = "ru_RU-denis-medium"


def _voice_dir() -> Path:
    from .. import paths

    return paths.models_dir() / "piper"


def download_voice(voice_id: str) -> Path:
    """Скачивает голос с HuggingFace и возвращает путь к файлу модели.

    Качаем напрямую через huggingface_hub, а не через piper.download_voices:
    hub уже стоит как зависимость faster-whisper, умеет кэшировать и
    докачивать, и кладёт файлы туда, куда скажем.
    """
    relative = _VOICE_PATHS.get(voice_id)
    if relative is None:
        raise TtsError(f"неизвестный голос Piper: {voice_id}")

    try:
        from huggingface_hub import hf_hub_download
    except ImportError as exc:
        raise TtsUnavailable("huggingface_hub не установлен") from exc

    target = _voice_dir()
    target.mkdir(parents=True, exist_ok=True)

    paths_out = []
    for suffix in (".onnx", ".onnx.json"):
        filename = f"{relative}/{voice_id}{suffix}"
        try:
            downloaded = hf_hub_download(
                repo_id=HF_REPO,
                filename=filename,
                local_dir=str(target),
            )
        except Exception as exc:
            raise TtsUnavailable(f"не удалось скачать голос {voice_id}: {exc}") from exc
        paths_out.append(Path(downloaded))

    log.info("Голос Piper %s готов: %s", voice_id, paths_out[0])
    return paths_out[0]


def voice_path(voice_id: str) -> Path | None:
    """Путь к уже скачанному голосу, если он есть."""
    relative = _VOICE_PATHS.get(voice_id)
    if relative is None:
        return None
    candidate = _voice_dir() / relative / f"{voice_id}.onnx"
    return candidate if candidate.exists() else None


class PiperTts:
    """Движок синтеза Piper."""

    name = "piper"
    title = "Piper"

    def __init__(self) -> None:
        self._voices: dict[str, object] = {}

    def is_available(self) -> bool:
        try:
            import piper  # noqa: F401
        except ImportError:
            return False
        return True

    def list_voices(self) -> list[Voice]:
        return list(VOICES)

    def _load(self, voice_id: str):
        cached = self._voices.get(voice_id)
        if cached is not None:
            return cached

        try:
            from piper import PiperVoice
        except ImportError as exc:
            raise TtsUnavailable("пакет piper-tts не установлен") from exc

        path = voice_path(voice_id) or download_voice(voice_id)
        try:
            voice = PiperVoice.load(str(path))
        except Exception as exc:
            raise TtsError(f"не удалось загрузить голос {voice_id}: {exc}") from exc

        self._voices[voice_id] = voice
        return voice

    def synthesize(self, text: str, voice: str, rate: int, pitch: int, out_path: Path) -> Path:
        voice_id = voice or DEFAULT_VOICE
        piper_voice = self._load(voice_id)

        # Piper не умеет менять высоту тона, только темп: length_scale больше
        # единицы растягивает речь. Проценты пользователя переводим в множитель.
        length_scale = 1.0 / (1.0 + rate / 100.0) if rate > -100 else 1.0

        try:
            from piper import SynthesisConfig

            config = SynthesisConfig(length_scale=length_scale)
        except Exception:
            config = None

        out_path = out_path.with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)

        try:
            with wave.open(str(out_path), "wb") as wav_file:
                if config is not None:
                    piper_voice.synthesize_wav(text, wav_file, syn_config=config)
                else:
                    piper_voice.synthesize_wav(text, wav_file)
        except Exception as exc:
            raise TtsError(f"Piper не смог озвучить текст: {exc}") from exc

        if not out_path.exists() or out_path.stat().st_size == 0:
            raise TtsError("Piper вернул пустой файл")

        if pitch:
            log.debug("Piper не поддерживает изменение высоты тона, параметр проигнорирован")

        log.info("Piper: озвучено голосом %s, %d байт", voice_id, out_path.stat().st_size)
        return out_path
