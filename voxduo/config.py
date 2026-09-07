"""Настройки приложения: значения по умолчанию, чтение, запись, миграция.

Конфиг хранится в JSON рядом с остальными пользовательскими данными.
Три вещи, которые здесь важнее удобства:

* Незнакомые поля из файла не теряются при чтении, а недостающие
  дополняются дефолтами — иначе обновление приложения обнуляло бы
  настройки пользователя.
* Битый JSON не мешает запуску: файл откладывается в сторону,
  приложение стартует с дефолтами.
* Запись атомарная, чтобы выключение питания посреди сохранения
  не оставило обрезанный файл.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

# Текущая версия схемы. Увеличивается при несовместимых изменениях,
# обрабатывается в _migrate().
SCHEMA_VERSION = 1

# Промпт задаёт Whisper стиль расшифровки. Главный рычаг против
# транслитерации английских терминов кириллицей: модель видит в примере
# латиницу и пунктуацию — и держит тот же регистр дальше.
DEFAULT_INITIAL_PROMPT = (
    "Обсуждаем разработку: Python, JavaScript, React, Docker, API, commit, "
    "merge request, pull request, CI/CD. Речь на русском с английскими терминами."
)

# Стартовый словарь замен. Пополняется пользователем из интерфейса.
DEFAULT_REPLACEMENTS: dict[str, str] = {
    "джаваскрипт": "JavaScript",
    "джава скрипт": "JavaScript",
    "питон": "Python",
    "гитхаб": "GitHub",
    "гит хаб": "GitHub",
    "докер": "Docker",
}


@dataclass
class SttConfig:
    """Распознавание речи."""

    model: str = "large-v3"          # large-v3 | large-v3-turbo
    language: str = "ru"             # ru | en | auto
    device: str = "auto"             # auto | cuda | cpu
    initial_prompt: str = DEFAULT_INITIAL_PROMPT
    beam_size: int = 5               # 1 = жадный поиск; 5 заметно ровнее пунктуация
    vad_filter: bool = True          # режет тишину, убирает галлюцинации
    vad_min_silence_ms: int = 500
    input_device: str | None = None  # None = устройство по умолчанию


@dataclass
class TtsConfig:
    """Синтез речи."""

    engine: str = "edge"
    fallback_order: list[str] = field(
        default_factory=lambda: ["edge", "silero", "piper"]
    )
    voices: dict[str, str] = field(
        default_factory=lambda: {
            "edge": "ru-RU-SvetlanaNeural",
            "silero": "",                     # заполнится первым голосом модели
            "piper": "ru_RU-denis-medium",    # CC0
        }
    )
    rate: int = 0    # проценты к скорости: -50..+100
    pitch: int = 0   # герцы к высоте тона
    # Пусто = использовать версию, зашитую в edge-tts. Ручное значение
    # позволяет починить 403 при ротации токена, не дожидаясь релиза пакета.
    edge_chromium_version: str = ""


@dataclass
class AppConfig:
    """Корень конфигурации."""

    schema_version: int = SCHEMA_VERSION
    theme: str = "system"   # system | light | dark
    mode: str = "stt"       # какой режим открыть при старте
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    replacements: dict[str, str] = field(
        default_factory=lambda: dict(DEFAULT_REPLACEMENTS)
    )

    def to_dict(self) -> dict[str, Any]:
        return dataclasses.asdict(self)


def _merge(defaults: dict[str, Any], stored: dict[str, Any]) -> dict[str, Any]:
    """Накладывает сохранённые значения на дефолты, рекурсивно по словарям.

    Ключи, которых нет в дефолтах, отбрасываются — так удалённая настройка
    не тянется из старого файла и не сбивает конструктор dataclass.
    """
    result = dict(defaults)
    for key, value in stored.items():
        if key not in defaults:
            continue
        default_value = defaults[key]
        if isinstance(default_value, dict) and isinstance(value, dict):
            # replacements и voices — пользовательские словари, их дополняем,
            # а не заменяем поэлементно как вложенную структуру настроек
            if key in ("replacements", "voices"):
                merged = dict(default_value)
                merged.update(value)
                result[key] = merged
            else:
                result[key] = _merge(default_value, value)
        else:
            result[key] = value
    return result


def _migrate(data: dict[str, Any]) -> dict[str, Any]:
    """Приводит конфиг старой версии к текущей схеме."""
    version = data.get("schema_version", 0)
    if version == SCHEMA_VERSION:
        return data
    if version > SCHEMA_VERSION:
        # Конфиг из более новой версии приложения: чужие поля всё равно
        # отсеет _merge, поэтому просто предупреждаем.
        log.warning("Конфиг версии %s новее поддерживаемой %s", version, SCHEMA_VERSION)
        return data
    # Здесь появятся преобразования, когда схема начнёт меняться.
    log.info("Конфиг мигрирован с версии %s на %s", version, SCHEMA_VERSION)
    data["schema_version"] = SCHEMA_VERSION
    return data


def _from_dict(data: dict[str, Any]) -> AppConfig:
    merged = _merge(AppConfig().to_dict(), data)
    merged.pop("schema_version", None)
    stt = SttConfig(**merged.pop("stt"))
    tts = TtsConfig(**merged.pop("tts"))
    return AppConfig(schema_version=SCHEMA_VERSION, stt=stt, tts=tts, **merged)


def load(path: Path | None = None) -> AppConfig:
    """Читает конфиг. При любой проблеме возвращает дефолты, не падая."""
    path = path or paths.config_file()
    if not path.exists():
        return AppConfig()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("ожидался объект JSON")
        return _from_dict(_migrate(raw))
    except Exception as exc:
        # Отложить битый файл важнее, чем сохранить его: иначе следующая
        # запись затрёт единственную улику.
        backup = path.with_suffix(".json.broken")
        try:
            shutil.copy2(path, backup)
        except OSError:
            backup = None
        log.error("Конфиг повреждён (%s), стартуем с дефолтами. Копия: %s", exc, backup)
        return AppConfig()


def save(config: AppConfig, path: Path | None = None) -> None:
    """Атомарно записывает конфиг: сначала во временный файл, потом замена."""
    path = path or paths.config_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(
        json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(tmp, path)
