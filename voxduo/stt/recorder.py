"""Запись с микрофона.

Отличия от первой версии проекта, каждое по делу:

* Поток останавливается по событию, а не циклом со sleep — стоп срабатывает
  сразу, а не с задержкой до сотни миллисекунд.
* Считается уровень сигнала, чтобы интерфейс показывал, что микрофон реально
  слышит голос. Раньше о неработающем микрофоне узнавали по пустой расшифровке.
* Устройство ввода выбирается явно: у кого гарнитура, веб-камера и встроенный
  микрофон одновременно, «устройство по умолчанию» — лотерея.
* Ошибка внутри звукового потока запоминается и поднимается при остановке,
  а не теряется в чужом потоке.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np
import sounddevice as sd

log = logging.getLogger(__name__)

# Whisper работает с 16 кГц моно; писать больше — впустую гонять данные
SAMPLE_RATE = 16_000
CHANNELS = 1
BLOCK_SIZE = 1024


@dataclass(frozen=True)
class InputDevice:
    """Устройство ввода в виде, пригодном для показа в списке."""

    index: int
    name: str
    default: bool

    def __str__(self) -> str:
        return f"{self.name} (по умолчанию)" if self.default else self.name


def list_input_devices() -> list[InputDevice]:
    """Микрофоны, доступные в системе."""
    try:
        devices = sd.query_devices()
        default_index = sd.default.device[0]
    except Exception as exc:
        log.error("Не удалось получить список устройств ввода: %s", exc)
        return []

    result: list[InputDevice] = []
    for index, device in enumerate(devices):
        if device.get("max_input_channels", 0) < 1:
            continue
        result.append(
            InputDevice(
                index=index,
                name=str(device.get("name", f"Устройство {index}")),
                default=(index == default_index),
            )
        )
    return result


def resolve_device(name: str | None) -> int | None:
    """Ищет устройство по имени. None означает «системное по умолчанию».

    Имя, а не индекс: индексы меняются при подключении новой гарнитуры,
    а сохранённая настройка должна переживать это.
    """
    if not name:
        return None
    for device in list_input_devices():
        if device.name == name:
            return device.index
    log.warning("Микрофон %r не найден, используем устройство по умолчанию", name)
    return None


class Recorder:
    """Запись в память до явной остановки."""

    def __init__(self, device_name: str | None = None) -> None:
        self._device_name = device_name
        self._stream: sd.InputStream | None = None
        self._chunks: list[np.ndarray] = []
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._level = 0.0
        self._error: Exception | None = None

    @property
    def is_recording(self) -> bool:
        return self._stream is not None

    @property
    def level(self) -> float:
        """Громкость последнего блока, 0.0–1.0. Для индикатора в интерфейсе."""
        return self._level

    def _callback(self, indata: np.ndarray, frames: int, time_info, status) -> None:
        if status:
            # Переполнение буфера при загруженной системе — не повод падать,
            # но знать об этом полезно
            log.debug("Статус звукового потока: %s", status)
        block = indata.copy()
        with self._lock:
            self._chunks.append(block)
        # Среднеквадратичное значение ближе к воспринимаемой громкости, чем пик
        self._level = float(min(1.0, np.sqrt(np.mean(np.square(block))) * 4.0))

    def start(self) -> None:
        if self._stream is not None:
            raise RuntimeError("Запись уже идёт")

        with self._lock:
            self._chunks = []
        self._stop_event.clear()
        self._error = None
        self._level = 0.0

        device = resolve_device(self._device_name)
        try:
            self._stream = sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=CHANNELS,
                blocksize=BLOCK_SIZE,
                dtype="float32",
                device=device,
                callback=self._callback,
            )
            self._stream.start()
        except Exception as exc:
            self._stream = None
            log.error("Не удалось открыть микрофон: %s", exc)
            raise

        log.info("Запись начата, устройство: %s", self._device_name or "по умолчанию")

    def stop(self) -> np.ndarray:
        """Останавливает запись и возвращает моно-дорожку float32.

        Пустой массив означает, что записать ничего не удалось — вызывающий
        код должен показать это пользователем, а не отправлять тишину в Whisper.
        """
        stream, self._stream = self._stream, None
        if stream is None:
            return np.zeros(0, dtype=np.float32)

        try:
            stream.stop()
            stream.close()
        except Exception as exc:
            log.error("Ошибка при остановке потока записи: %s", exc)

        self._stop_event.set()
        self._level = 0.0

        with self._lock:
            chunks = self._chunks
            self._chunks = []

        if not chunks:
            log.warning("Запись пуста: микрофон не дал ни одного блока")
            return np.zeros(0, dtype=np.float32)

        audio = np.concatenate(chunks, axis=0).reshape(-1).astype(np.float32)
        log.info("Записано %.1f с звука", len(audio) / SAMPLE_RATE)
        return audio

    def cancel(self) -> None:
        """Останавливает запись и выбрасывает накопленное."""
        self.stop()


def duration_seconds(audio: np.ndarray) -> float:
    return len(audio) / SAMPLE_RATE if len(audio) else 0.0
