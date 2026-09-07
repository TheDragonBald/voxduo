"""Распознавание речи на faster-whisper.

Здесь собраны решения, которые и дают прирост качества относительно
первой версии проекта:

* Модель загружается лениво и в фоне, а не на старте — окно больше не висит
  несколько секунд при запуске.
* Устройство выбирается автоматически: видеокарта с float16, иначе процессор
  с int8. Одна и та же сборка работает и на машине без CUDA.
* Декодирование лучевым поиском вместо жадного: заметно ровнее пунктуация.
* Фильтр тишины (Silero VAD) — против галлюцинаций вроде «Продолжение
  следует…», которые Whisper дописывает на паузах.
* initial_prompt задаёт стиль расшифровки и удерживает английские термины
  в латинице.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .. import cuda_setup
from ..config import SttConfig
from . import postprocess

log = logging.getLogger(__name__)

# Понятные названия для интерфейса
MODEL_CHOICES: dict[str, str] = {
    "large-v3": "large-v3 — максимум точности (3.1 ГБ)",
    "large-v3-turbo": "large-v3-turbo — быстрее в 3–4 раза (1.6 ГБ)",
}

LANGUAGE_CHOICES: dict[str, str] = {
    "ru": "Русский",
    "en": "Английский",
    "auto": "Определять автоматически",
}

# Температуры для отката: если декодирование на нуле выдало подозрительный
# результат, faster-whisper пробует следующие значения
TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


@dataclass(frozen=True)
class TranscriptionResult:
    """Результат распознавания вместе с тем, что полезно записать в историю."""

    text: str
    language: str
    language_probability: float
    audio_seconds: float
    elapsed_seconds: float
    model: str
    device: str

    @property
    def speed_ratio(self) -> float:
        """Во сколько раз быстрее реального времени. Ноль, если считать не из чего."""
        if self.elapsed_seconds <= 0:
            return 0.0
        return self.audio_seconds / self.elapsed_seconds


class ModelLoadError(RuntimeError):
    """Модель не удалось загрузить: нет сети при первом запуске или мало памяти."""


class SttEngine:
    """Обёртка над WhisperModel с ленивой загрузкой и сменой модели."""

    def __init__(self, config: SttConfig) -> None:
        self._config = config
        self._model = None
        self._loaded_key: tuple[str, str, str] | None = None
        self._device = "cpu"
        self._compute_type = "int8"

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    @property
    def device(self) -> str:
        return self._device

    def update_config(self, config: SttConfig) -> None:
        """Новые настройки. Модель перезагрузится, только если это правда нужно."""
        self._config = config

    def _target_key(self) -> tuple[str, str, str]:
        device, compute_type = cuda_setup.resolve_device(self._config.device)
        return self._config.model, device, compute_type

    def ensure_loaded(self, on_status: Callable[[str], None] | None = None) -> None:
        """Загружает модель, если ещё не загружена или сменились модель/устройство.

        Первый вызов для новой модели качает её с HuggingFace — это несколько
        гигабайт, поэтому статус стоит показать пользователю.
        """
        key = self._target_key()
        if self._model is not None and self._loaded_key == key:
            return

        model_name, device, compute_type = key
        from .. import paths

        models_dir = paths.models_dir()
        models_dir.mkdir(parents=True, exist_ok=True)

        # Импорт здесь, а не наверху: к этому моменту cuda_setup уже
        # зарегистрировал каталоги с DLL
        from faster_whisper import WhisperModel

        if on_status:
            on_status(f"Загрузка модели {model_name} ({device})…")
        log.info("Загружаем модель %s на %s / %s", model_name, device, compute_type)

        started = time.monotonic()
        try:
            self._model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=str(models_dir),
            )
        except Exception as exc:
            self._model = None
            self._loaded_key = None
            log.exception("Не удалось загрузить модель %s", model_name)
            raise ModelLoadError(str(exc)) from exc

        self._loaded_key = key
        self._device = device
        self._compute_type = compute_type
        log.info("Модель готова за %.1f с", time.monotonic() - started)

    def unload(self) -> None:
        """Освобождает видеопамять — пригодится при смене модели."""
        self._model = None
        self._loaded_key = None

    def transcribe(
        self,
        audio: np.ndarray | Path | str,
        replacements: dict[str, str] | None = None,
        on_status: Callable[[str], None] | None = None,
    ) -> TranscriptionResult:
        """Распознаёт запись и приводит текст в читаемый вид."""
        self.ensure_loaded(on_status)
        if self._model is None:
            raise ModelLoadError("модель не загружена")

        config = self._config
        language = None if config.language == "auto" else config.language

        vad_parameters = {"min_silence_duration_ms": config.vad_min_silence_ms}

        if on_status:
            on_status("Распознавание…")

        started = time.monotonic()
        segments, info = self._model.transcribe(
            audio if isinstance(audio, np.ndarray) else str(audio),
            language=language,
            beam_size=config.beam_size,
            vad_filter=config.vad_filter,
            vad_parameters=vad_parameters,
            condition_on_previous_text=False,
            temperature=list(TEMPERATURE_FALLBACK),
            initial_prompt=config.initial_prompt or None,
        )

        # segments — ленивый генератор: работа начинается только здесь
        raw_text = " ".join(segment.text.strip() for segment in segments).strip()
        elapsed = time.monotonic() - started

        text = postprocess.postprocess(raw_text, replacements)

        result = TranscriptionResult(
            text=text,
            language=getattr(info, "language", language or "?"),
            language_probability=float(getattr(info, "language_probability", 0.0) or 0.0),
            audio_seconds=float(getattr(info, "duration", 0.0) or 0.0),
            elapsed_seconds=elapsed,
            model=config.model,
            device=self._device,
        )

        # Текст в лог не пишем: содержимое речи остаётся приватным
        log.info(
            "Распознано: %.1f с звука за %.1f с (x%.1f), язык %s, символов %d",
            result.audio_seconds,
            result.elapsed_seconds,
            result.speed_ratio,
            result.language,
            len(result.text),
        )
        return result
