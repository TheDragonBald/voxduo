"""Синтез через Silero — офлайн, на процессоре.

По умолчанию берём модель v5_cis_base, и это осознанный выбор. Основные
русские модели Silero (v5_ru, v5_5_ru) выпущены под CC BY-NC, то есть
запрещают коммерческое использование, а v5_cis_base — под MIT. При этом
качеством она не уступает: в независимом сравнении русских синтезаторов
её оценка натуральности 3.04 UTMOS против 3.08 у живых записей.

Модель качаем прямо по ссылке и открываем через torch.package, а не через
torch.hub.load: последний тянет за собой клон репозитория с GitHub, что
лишний раз ломается на машинах без git и в закрытых сетях.

Список голосов читаем из самой модели: в models.yml его нет, а хардкод
рассыплется при смене версии.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

from .base import TtsError, TtsUnavailable, Voice

log = logging.getLogger(__name__)

# Модель под MIT. Альтернативы (v5_ru, v5_5_ru) звучат похоже, но под CC BY-NC.
MODEL_ID = "v5_cis_base"
MODEL_URL = f"https://models.silero.ai/models/tts/ru/{MODEL_ID}.pt"
MODEL_LICENSE = "MIT"

SAMPLE_RATE = 48_000

# Silero принимает ударения через плюс перед гласной: «к+ошка»
STRESS_HINT = "ударения можно задавать плюсом: к+ошка"


# Языки не-русских голосов модели, чтобы список читался осмысленно
LANGUAGE_NAMES: dict[str, str] = {
    "bak": "башкирский",
    "tat": "татарский",
    "erz": "эрзянский",
    "kaz": "казахский",
    "uzb": "узбекский",
    "tgk": "таджикский",
    "kir": "киргизский",
    "aze": "азербайджанский",
    "hye": "армянский",
    "kat": "грузинский",
    "bel": "белорусский",
    "ukr": "украинский",
    "mol": "молдавский",
    "cv": "чувашский",
    "chv": "чувашский",
    "kalm": "калмыцкий",
    "sah": "якутский",
    "udm": "удмуртский",
    "kbd": "кабардинский",
    "oss": "осетинский",
}


def _model_path() -> Path:
    from .. import paths

    return paths.models_dir() / "silero" / f"{MODEL_ID}.pt"


class SileroTts:
    """Движок синтеза Silero."""

    name = "silero"
    title = "Silero"

    def __init__(self) -> None:
        self._model = None
        self._speakers: list[str] = []
        self._lock = threading.Lock()

    def is_available(self) -> bool:
        """Нужен torch. Он ставится отдельно, потому что нужен только здесь."""
        try:
            import torch  # noqa: F401
        except ImportError:
            return False
        return True

    def _ensure_downloaded(self) -> Path:
        path = _model_path()
        if path.exists() and path.stat().st_size > 0:
            return path

        try:
            import torch
        except ImportError as exc:
            raise TtsUnavailable("torch не установлен: pip install -r requirements-silero.txt") from exc

        path.parent.mkdir(parents=True, exist_ok=True)
        log.info("Скачиваем модель Silero %s", MODEL_ID)
        try:
            torch.hub.download_url_to_file(MODEL_URL, str(path), progress=False)
        except Exception as exc:
            # Частично скачанный файл хуже отсутствующего: следующий запуск
            # решит, что модель на месте, и упадёт при загрузке
            path.unlink(missing_ok=True)
            raise TtsUnavailable(f"не удалось скачать модель Silero: {exc}") from exc
        return path

    def _load(self):
        if self._model is not None:
            return self._model

        with self._lock:
            if self._model is not None:
                return self._model

            try:
                import torch
            except ImportError as exc:
                raise TtsUnavailable("torch не установлен") from exc

            path = self._ensure_downloaded()
            try:
                importer = torch.package.PackageImporter(str(path))
                model = importer.load_pickle("tts_models", "model")
                model.to(torch.device("cpu"))
            except Exception as exc:
                raise TtsError(f"не удалось открыть модель Silero: {exc}") from exc

            self._model = model
            self._speakers = [s for s in getattr(model, "speakers", []) if s != "random"]
            log.info("Silero готов, голосов: %d", len(self._speakers))
            return model

    def list_voices(self) -> list[Voice]:
        """Голоса читаются из модели, поэтому список требует её загрузки."""
        try:
            self._load()
        except TtsError as exc:
            log.info("Список голосов Silero недоступен: %s", exc)
            return []

        # v5_cis_base мультиязычная: помимо русских голосов в ней башкирские,
        # татарские, эрзянские и другие. Имена вида ru_aidar, bak_aigul.
        # Русские поднимаем наверх, иначе первым в списке окажется голос на
        # языке, которого пользователь не ждёт.
        russian: list[Voice] = []
        other: list[Voice] = []

        for speaker in self._speakers:
            prefix, _, rest = speaker.partition("_")
            is_russian = prefix == "ru" or not rest
            label = (rest or speaker).replace("_", " ").capitalize()
            language = LANGUAGE_NAMES.get(prefix, prefix) if not is_russian else ""
            voice = Voice(
                id=speaker,
                label=label if is_russian else f"{label} ({language})",
                license=MODEL_LICENSE,
            )
            (russian if is_russian else other).append(voice)

        return russian + other

    def default_voice(self) -> str:
        """Первый русский голос модели."""
        self._load()
        for speaker in self._speakers:
            if speaker.startswith("ru_"):
                return speaker
        return self._speakers[0] if self._speakers else ""

    def synthesize(self, text: str, voice: str, rate: int, pitch: int, out_path: Path) -> Path:
        model = self._load()
        speaker = voice or self.default_voice()
        if speaker not in self._speakers:
            raise TtsError(f"голос {speaker!r} отсутствует в модели")

        try:
            import numpy as np
            import soundfile as sf
        except ImportError as exc:
            raise TtsUnavailable("нет numpy или soundfile") from exc

        try:
            audio = model.apply_tts(text=text, speaker=speaker, sample_rate=SAMPLE_RATE)
        except Exception as exc:
            raise TtsError(f"Silero не смог озвучить текст: {exc}") from exc

        samples = audio.detach().cpu().numpy().astype("float32")
        if samples.size == 0:
            raise TtsError("Silero вернул пустой звук")

        # Темп меняем передискретизацией: своего параметра скорости у модели нет
        if rate:
            factor = 1.0 + rate / 100.0
            if factor > 0:
                indices = np.arange(0, len(samples), factor)
                samples = np.interp(indices, np.arange(len(samples)), samples).astype("float32")

        out_path = out_path.with_suffix(".wav")
        out_path.parent.mkdir(parents=True, exist_ok=True)
        sf.write(str(out_path), samples, SAMPLE_RATE)

        if pitch:
            log.debug("Silero не поддерживает изменение высоты тона, параметр проигнорирован")

        log.info("Silero: озвучено голосом %s, %d байт", speaker, out_path.stat().st_size)
        return out_path
