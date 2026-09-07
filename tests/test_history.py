"""Тесты истории.

Здесь легко получить два тихих дефекта: потерять записи пользователя при
повреждении файла и оставить после себя гору аудиофайлов, на которые уже
никто не ссылается. Обе вещи не видны при обычном использовании, поэтому
проверяются тестами.
"""

from __future__ import annotations

import json

import pytest

from voxduo.history import History, SttEntry, TtsEntry


@pytest.fixture
def history(tmp_path):
    return History(path=tmp_path / "history.json", audio_dir=tmp_path / "audio", limit=5)


def _audio_file(history: History, name: str):
    history.audio_dir.mkdir(parents=True, exist_ok=True)
    path = history.audio_dir / name
    path.write_bytes(b"fake audio")
    return path


# --- очереди ---


def test_newest_entry_comes_first(history):
    history.add_stt(SttEntry(text="первая"))
    history.add_stt(SttEntry(text="вторая"))
    assert [e.text for e in history.stt] == ["вторая", "первая"]


def test_queue_is_capped(history):
    for i in range(8):
        history.add_stt(SttEntry(text=f"запись {i}"))
    assert len(history.stt) == 5
    assert history.stt[0].text == "запись 7"
    assert history.stt[-1].text == "запись 3"


def test_queues_are_independent(history):
    history.add_stt(SttEntry(text="расшифровка"))
    history.add_tts(TtsEntry(text="озвучка"))
    assert len(history.stt) == 1
    assert len(history.tts) == 1


# --- аудиофайлы ---


def test_evicted_tts_audio_is_deleted(history):
    kept, dropped = [], None
    for i in range(6):
        name = f"audio{i}.wav"
        _audio_file(history, name)
        history.add_tts(TtsEntry(text=f"текст {i}", audio_name=name))
        if i == 0:
            dropped = name
        else:
            kept.append(name)

    assert not (history.audio_dir / dropped).exists(), "файл вытесненной записи должен исчезнуть"
    for name in kept:
        assert (history.audio_dir / name).exists()


def test_clear_removes_all_audio(history):
    for i in range(3):
        name = f"audio{i}.wav"
        _audio_file(history, name)
        history.add_tts(TtsEntry(text=f"текст {i}", audio_name=name))

    history.clear()

    assert history.tts == []
    assert list(history.audio_dir.iterdir()) == []


def test_orphan_audio_cleaned_on_load(history, tmp_path):
    """Файл без записи остаётся после падения между сохранением файла и истории."""
    _audio_file(history, "живой.wav")
    history.add_tts(TtsEntry(text="есть запись", audio_name="живой.wav"))
    _audio_file(history, "осиротевший.wav")

    reopened = History(path=tmp_path / "history.json", audio_dir=tmp_path / "audio", limit=5)
    reopened.load()

    assert (history.audio_dir / "живой.wav").exists()
    assert not (history.audio_dir / "осиротевший.wav").exists()


def test_missing_audio_forgotten_but_entry_kept(history, tmp_path):
    """Пользователь удалил файл вручную — текст всё равно должен остаться."""
    _audio_file(history, "пропадёт.wav")
    history.add_tts(TtsEntry(text="важный текст", audio_name="пропадёт.wav"))
    (history.audio_dir / "пропадёт.wav").unlink()

    reopened = History(path=tmp_path / "history.json", audio_dir=tmp_path / "audio", limit=5)
    reopened.load()

    assert reopened.tts[0].text == "важный текст"
    assert reopened.tts[0].audio_name == ""
    assert reopened.tts[0].audio_path(reopened.audio_dir) is None


def test_store_audio_gives_unique_names(history, tmp_path):
    source = tmp_path / "source.wav"
    source.write_bytes(b"audio")
    first = history.store_audio(source)
    second = history.store_audio(source)
    assert first != second, "одинаковые имена затирали бы предыдущую озвучку"
    assert (history.audio_dir / first).exists()
    assert (history.audio_dir / second).exists()


# --- сохранение и чтение ---


def test_survives_restart(history, tmp_path):
    history.add_stt(SttEntry(text="переживёт перезапуск", model="large-v3", language="ru"))
    history.add_tts(TtsEntry(text="и это тоже", engine="edge", voice="ru-RU-SvetlanaNeural"))

    reopened = History(path=tmp_path / "history.json", audio_dir=tmp_path / "audio", limit=5)
    reopened.load()

    assert reopened.stt[0].text == "переживёт перезапуск"
    assert reopened.stt[0].model == "large-v3"
    assert reopened.tts[0].engine == "edge"


def test_load_without_file_is_quiet(tmp_path):
    history = History(path=tmp_path / "нет.json", audio_dir=tmp_path / "audio")
    history.load()
    assert history.stt == [] and history.tts == []


def test_broken_json_does_not_break_startup(history, tmp_path):
    history._path.parent.mkdir(parents=True, exist_ok=True)
    history._path.write_text("{ сломано", encoding="utf-8")
    history.load()
    assert history.stt == [] and history.tts == []


def test_damaged_entries_are_skipped(history, tmp_path):
    """Одна битая запись не должна утащить за собой остальные."""
    history._path.parent.mkdir(parents=True, exist_ok=True)
    history._path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "stt": [
                    {"text": "хорошая"},
                    {"нет текста": True},
                    "вообще не объект",
                    {"text": "тоже хорошая"},
                ],
                "tts": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    history.load()
    assert [e.text for e in history.stt] == ["хорошая", "тоже хорошая"]


def test_unknown_fields_ignored(history):
    history._path.parent.mkdir(parents=True, exist_ok=True)
    history._path.write_text(
        json.dumps({"stt": [{"text": "запись", "поле_из_будущего": 1}], "tts": []}),
        encoding="utf-8",
    )
    history.load()
    assert history.stt[0].text == "запись"


def test_load_respects_limit(history):
    history._path.parent.mkdir(parents=True, exist_ok=True)
    history._path.write_text(
        json.dumps({"stt": [{"text": f"n{i}"} for i in range(20)], "tts": []}),
        encoding="utf-8",
    )
    history.load()
    assert len(history.stt) == 5


# --- отображение ---


def test_preview_is_single_line_and_short():
    entry = SttEntry(text="строка\nс переносом   и   лишними пробелами " + "x" * 100)
    assert "\n" not in entry.preview
    assert len(entry.preview) <= 60


def test_short_text_preview_unchanged():
    assert SttEntry(text="коротко").preview == "коротко"


def test_time_label_from_timestamp():
    assert SttEntry(text="t", timestamp="2026-09-07T14:32:00").time_label == "14:32"


def test_time_label_survives_garbage():
    assert SttEntry(text="t", timestamp="не время").time_label == "--:--"
