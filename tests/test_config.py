"""Тесты конфигурации.

Проверяем то, что ломается тихо: пользователь обновил приложение и потерял
настройки, или файл повредился и приложение перестало запускаться.
"""

from __future__ import annotations

import json

import pytest

from voxduo import config


def test_defaults_are_sane():
    cfg = config.AppConfig()
    assert cfg.schema_version == config.SCHEMA_VERSION
    assert cfg.theme == "system"
    assert cfg.stt.model == "large-v3"
    assert cfg.stt.beam_size == 5, "жадный поиск заметно хуже по пунктуации"
    assert cfg.stt.vad_filter is True
    assert cfg.tts.fallback_order == ["edge", "silero", "piper"]
    # Голос Piper по умолчанию обязан быть под CC0
    assert cfg.tts.voices["piper"] in ("ru_RU-denis-medium", "ru_RU-dmitri-medium")


def test_missing_file_gives_defaults(tmp_path):
    cfg = config.load(tmp_path / "нет-такого.json")
    assert cfg.stt.model == "large-v3"


def test_roundtrip(tmp_path):
    path = tmp_path / "config.json"
    cfg = config.AppConfig()
    cfg.theme = "dark"
    cfg.stt.model = "large-v3-turbo"
    cfg.stt.language = "auto"
    cfg.tts.rate = -10
    config.save(cfg, path)

    loaded = config.load(path)
    assert loaded.theme == "dark"
    assert loaded.stt.model == "large-v3-turbo"
    assert loaded.stt.language == "auto"
    assert loaded.tts.rate == -10


def test_save_is_atomic(tmp_path):
    path = tmp_path / "config.json"
    config.save(config.AppConfig(), path)
    assert path.exists()
    # Временный файл не должен оставаться после успешной записи
    assert not (tmp_path / "config.json.tmp").exists()


def test_partial_config_filled_with_defaults(tmp_path):
    """Обновление приложения не должно обнулять то, чего не было в старом файле."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"schema_version": 1, "theme": "light"}, ensure_ascii=False),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.theme == "light"
    assert cfg.stt.model == "large-v3"
    assert cfg.tts.engine == "edge"


def test_unknown_keys_are_dropped(tmp_path):
    """Удалённая когда-то настройка не должна ломать конструктор."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"schema_version": 1, "theme": "dark", "давно_удалено": 42}),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.theme == "dark"
    assert not hasattr(cfg, "давно_удалено")


def test_broken_json_does_not_break_startup(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{ это не json", encoding="utf-8")

    cfg = config.load(path)

    assert cfg.theme == "system", "должны получить дефолты, а не исключение"
    backup = path.with_suffix(".json.broken")
    assert backup.exists(), "битый файл нужно сохранить как улику"
    assert "это не json" in backup.read_text(encoding="utf-8")


def test_json_array_instead_of_object(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    cfg = config.load(path)
    assert cfg.theme == "system"


def test_replacements_merge_keeps_user_and_defaults(tmp_path):
    """Свои замены пользователя добавляются к встроенным, а не затирают их."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps(
            {"schema_version": 1, "replacements": {"кубернетес": "Kubernetes"}},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.replacements["кубернетес"] == "Kubernetes"
    assert cfg.replacements["питон"] == "Python", "встроенные замены должны остаться"


def test_voices_merge_partial(tmp_path):
    """Смена голоса одного движка не должна обнулять голоса остальных."""
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"schema_version": 1, "tts": {"voices": {"edge": "ru-RU-DmitryNeural"}}}),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.tts.voices["edge"] == "ru-RU-DmitryNeural"
    assert cfg.tts.voices["piper"] == "ru_RU-denis-medium"


def test_migration_from_versionless_config(tmp_path):
    """Конфиг без номера схемы читается и получает актуальную версию."""
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"theme": "dark"}), encoding="utf-8")
    cfg = config.load(path)
    assert cfg.schema_version == config.SCHEMA_VERSION
    assert cfg.theme == "dark"


def test_config_from_newer_version_does_not_crash(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(
        json.dumps({"schema_version": config.SCHEMA_VERSION + 5, "theme": "dark"}),
        encoding="utf-8",
    )
    cfg = config.load(path)
    assert cfg.theme == "dark"


@pytest.mark.parametrize("text", ["", "   ", "null"])
def test_empty_or_null_file(tmp_path, text):
    path = tmp_path / "config.json"
    path.write_text(text, encoding="utf-8")
    assert config.load(path).theme == "system"
