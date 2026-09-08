"""История последних расшифровок и озвучек.

Две независимые очереди по пять записей, общий файл JSON. Живёт между
запусками: закрыл приложение, открыл — последние пять на месте.

Отдельная забота — аудиофайлы озвучек. Они лежат рядом с историей, чтобы
переслушивать без повторного синтеза, но должны исчезать вместе с записью,
которую вытеснили. Иначе папка растёт бесконечно, и особенно заметно это
на длинных текстах.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

SCHEMA_VERSION = 1
DEFAULT_LIMIT = 5


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _preview(text: str, limit: int = 60) -> str:
    """Однострочный фрагмент для списка."""
    flat = " ".join(text.split())
    return flat if len(flat) <= limit else flat[: limit - 1] + "…"


def _time_label(timestamp: str) -> str:
    try:
        return datetime.fromisoformat(timestamp).strftime("%H:%M")
    except ValueError:
        return "--:--"


@dataclass
class SttEntry:
    """Расшифровка."""

    text: str
    timestamp: str = field(default_factory=_now)
    audio_seconds: float = 0.0
    elapsed_seconds: float = 0.0
    model: str = ""
    language: str = ""

    @property
    def preview(self) -> str:
        return _preview(self.text)

    @property
    def time_label(self) -> str:
        return _time_label(self.timestamp)


@dataclass
class TtsEntry:
    """Озвучка вместе с файлом, чтобы переслушать без пересинтеза."""

    text: str
    timestamp: str = field(default_factory=_now)
    engine: str = ""
    voice: str = ""
    audio_name: str = ""  # имя файла внутри папки audio, не полный путь

    @property
    def preview(self) -> str:
        return _preview(self.text)

    @property
    def time_label(self) -> str:
        return _time_label(self.timestamp)

    def audio_path(self, audio_dir: Path | None = None) -> Path | None:
        if not self.audio_name:
            return None
        directory = audio_dir or paths.audio_dir()
        candidate = directory / self.audio_name
        return candidate if candidate.exists() else None


class History:
    """Две очереди фиксированной длины с сохранением на диск."""

    def __init__(
        self,
        path: Path | None = None,
        audio_dir: Path | None = None,
        limit: int = DEFAULT_LIMIT,
    ) -> None:
        self._path = path or paths.history_file()
        self._audio_dir = audio_dir or paths.audio_dir()
        self._limit = limit
        self.stt: list[SttEntry] = []
        self.tts: list[TtsEntry] = []

    @property
    def limit(self) -> int:
        return self._limit

    @property
    def audio_dir(self) -> Path:
        return self._audio_dir

    # --- изменение ---

    def add_stt(self, entry: SttEntry) -> None:
        self.stt.insert(0, entry)
        del self.stt[self._limit :]
        self.save()

    def add_tts(self, entry: TtsEntry) -> None:
        self.tts.insert(0, entry)
        dropped = self.tts[self._limit :]
        del self.tts[self._limit :]
        for old in dropped:
            self._remove_audio(old)
        self.save()

    def clear(self) -> None:
        for entry in self.tts:
            self._remove_audio(entry)
        self.stt.clear()
        self.tts.clear()
        self.save()

    def _remove_audio(self, entry: TtsEntry) -> None:
        path = entry.audio_path(self._audio_dir)
        if path is None:
            return
        try:
            path.unlink()
            log.debug("Удалён аудиофайл вытесненной записи: %s", path.name)
        except OSError as exc:
            log.warning("Не удалось удалить %s: %s", path, exc)

    def store_audio(self, source: Path) -> str:
        """Переносит файл озвучки в папку истории и возвращает его имя.

        Имя делаем уникальным по времени: пользователь может озвучить один и
        тот же текст дважды разными голосами, и второй файл не должен затирать
        первый, пока обе записи в истории.
        """
        self._audio_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        target = self._audio_dir / (stamp + source.suffix)
        shutil.copy2(source, target)
        return target.name

    # --- хранение ---

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": SCHEMA_VERSION,
            "stt": [dataclasses.asdict(e) for e in self.stt],
            "tts": [dataclasses.asdict(e) for e in self.tts],
        }

    def save(self) -> None:
        """Атомарная запись: обрыв посреди сохранения не оставит битый файл."""
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".json.tmp")
        try:
            tmp.write_text(
                json.dumps(self.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except OSError as exc:
            # История — не то, ради чего стоит ронять приложение
            log.error("Не удалось сохранить историю: %s", exc)

    def load(self) -> None:
        """Читает историю. Битый файл не мешает запуску: начинаем с пустой."""
        if not self._path.exists():
            return
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("ожидался объект JSON")
        except Exception as exc:
            log.error("История повреждена (%s), начинаем с пустой", exc)
            self.stt = []
            self.tts = []
            return

        self.stt = _parse_list(raw.get("stt"), SttEntry)[: self._limit]
        self.tts = _parse_list(raw.get("tts"), TtsEntry)[: self._limit]
        self._forget_missing_audio()
        self._remove_orphan_audio()

    def _forget_missing_audio(self) -> None:
        """Если файл озвучки пропал, запись остаётся, но без кнопки воспроизведения."""
        for entry in self.tts:
            if entry.audio_name and entry.audio_path(self._audio_dir) is None:
                log.info("Аудиофайл %s пропал, запись останется без звука", entry.audio_name)
                entry.audio_name = ""

    def _remove_orphan_audio(self) -> None:
        """Подчищает файлы, на которые больше никто не ссылается.

        Такое остаётся после падения приложения между записью файла и
        сохранением истории.
        """
        if not self._audio_dir.exists():
            return
        referenced = {e.audio_name for e in self.tts if e.audio_name}
        for path in self._audio_dir.iterdir():
            if path.is_file() and path.name not in referenced:
                try:
                    path.unlink()
                    log.debug("Удалён осиротевший аудиофайл: %s", path.name)
                except OSError as exc:
                    log.warning("Не удалось удалить %s: %s", path, exc)


def _parse_list(raw: Any, cls: Any) -> list[Any]:
    """Разбирает список записей, пропуская повреждённые."""
    if not isinstance(raw, list):
        return []
    known = {f.name for f in dataclasses.fields(cls)}
    result = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        filtered = {k: v for k, v in item.items() if k in known}
        if not filtered.get("text"):
            continue
        try:
            result.append(cls(**filtered))
        except TypeError as exc:
            log.debug("Пропущена повреждённая запись истории: %s", exc)
    return result
