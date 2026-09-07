"""Воспроизведение синтезированной речи.

Отдельных зависимостей не потребовалось: soundfile собран с libsndfile,
который читает и MP3 от edge-tts, и WAV от Silero с Piper, а играет всё это
уже установленный sounddevice. Если сборка libsndfile окажется без MPEG,
подхватывается av — он всё равно стоит как зависимость faster-whisper.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)


class PlaybackError(RuntimeError):
    """Не удалось прочитать или воспроизвести файл."""


def _read_with_av(path: Path) -> tuple[np.ndarray, int]:
    """Запасной декодер на случай libsndfile без поддержки MP3."""
    try:
        import av
    except ImportError as exc:
        raise PlaybackError("нечем декодировать: нет ни libsndfile с MP3, ни av") from exc

    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise PlaybackError("в файле нет звуковой дорожки")
        sample_rate = stream.codec_context.sample_rate
        chunks = [frame.to_ndarray().reshape(-1) for frame in container.decode(stream)]

    if not chunks:
        raise PlaybackError("файл не содержит звука")
    return np.concatenate(chunks).astype(np.float32), int(sample_rate)


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    """Читает звук в моно float32 и возвращает его вместе с частотой."""
    try:
        import soundfile as sf

        data, sample_rate = sf.read(str(path), dtype="float32", always_2d=False)
    except Exception as exc:
        log.debug("soundfile не справился с %s (%s), пробуем av", path.name, exc)
        return _read_with_av(path)

    if data.ndim > 1:
        data = data.mean(axis=1)
    return data.astype(np.float32), int(sample_rate)


class Player:
    """Проигрыватель одной дорожки за раз."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._playing = False
        self._on_finish = None

    @property
    def is_playing(self) -> bool:
        return self._playing

    def play(self, path: Path, on_finish=None) -> None:
        """Начинает воспроизведение, не блокируя вызывающий поток."""
        path = Path(path)
        if not path.exists():
            raise PlaybackError(f"файл не найден: {path}")

        data, sample_rate = read_audio(path)
        if data.size == 0:
            raise PlaybackError("файл не содержит звука")

        with self._lock:
            self.stop()
            self._on_finish = on_finish
            try:
                sd.play(data, sample_rate)
            except Exception as exc:
                raise PlaybackError(f"не удалось воспроизвести: {exc}") from exc
            self._playing = True

        threading.Thread(target=self._wait_done, name="playback", daemon=True).start()
        log.debug("Воспроизведение %s, %.1f с", path.name, len(data) / sample_rate)

    def _wait_done(self) -> None:
        try:
            sd.wait()
        except Exception as exc:
            log.debug("Ожидание конца воспроизведения прервано: %s", exc)
        finally:
            self._playing = False
            callback, self._on_finish = self._on_finish, None
            if callback is not None:
                callback()

    def stop(self) -> None:
        """Останавливает воспроизведение. Безопасно вызывать, когда ничего не играет."""
        try:
            sd.stop()
        except Exception as exc:
            log.debug("Ошибка при остановке воспроизведения: %s", exc)
        self._playing = False
