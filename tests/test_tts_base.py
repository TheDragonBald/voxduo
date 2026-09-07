"""Тесты цепочки переключения между движками синтеза.

Ветвление, которое руками почти не проверить: чтобы увидеть фолбэк живьём,
пришлось бы дождаться, пока Microsoft сломает токен. Поэтому моки.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from voxduo.tts import base


class FakeEngine:
    """Движок-заглушка с управляемым поведением."""

    def __init__(self, name: str, available: bool = True, fails: bool = False) -> None:
        self.name = name
        self.title = name.capitalize()
        self._available = available
        self._fails = fails
        self.calls = 0

    def is_available(self) -> bool:
        return self._available

    def list_voices(self) -> list[base.Voice]:
        return [base.Voice(self.name + "-voice", self.name)]

    def synthesize(self, text: str, voice: str, rate: int, pitch: int, out_path: Path) -> Path:
        self.calls += 1
        if self._fails:
            raise base.TtsError("движок сломался")
        out_path = out_path.with_suffix(".wav")
        out_path.write_bytes(b"fake audio")
        return out_path


def _voices() -> dict[str, str]:
    return {"edge": "edge-voice", "silero": "silero-voice", "piper": "piper-voice"}


def test_build_order_puts_selected_first():
    assert base.build_order("silero", ["edge", "silero", "piper"]) == ["silero", "edge", "piper"]


def test_build_order_without_preference():
    assert base.build_order("", ["edge", "silero"]) == ["edge", "silero"]


def test_first_engine_wins_without_warning(tmp_path):
    engines = {"edge": FakeEngine("edge"), "silero": FakeEngine("silero")}
    outcome = base.synthesize_with_fallback(
        engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
    )
    assert outcome.engine == "edge"
    assert outcome.warning is None, "подмены не было, предупреждать не о чем"
    assert engines["silero"].calls == 0, "второй движок не должен вызываться зря"


def test_falls_back_when_unavailable(tmp_path):
    engines = {"edge": FakeEngine("edge", available=False), "silero": FakeEngine("silero")}
    outcome = base.synthesize_with_fallback(
        engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
    )
    assert outcome.engine == "silero"
    assert outcome.warning is not None, "пользователь должен узнать о подмене голоса"
    assert "Edge" in outcome.warning


def test_falls_back_when_engine_raises(tmp_path):
    engines = {"edge": FakeEngine("edge", fails=True), "silero": FakeEngine("silero")}
    outcome = base.synthesize_with_fallback(
        engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
    )
    assert outcome.engine == "silero"
    assert engines["edge"].calls == 1, "сначала должна быть попытка"


def test_unexpected_exception_also_triggers_fallback(tmp_path):
    class Exploding(FakeEngine):
        def synthesize(self, *args, **kwargs):
            raise ValueError("что-то совсем неожиданное")

    engines = {"edge": Exploding("edge"), "silero": FakeEngine("silero")}
    outcome = base.synthesize_with_fallback(
        engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
    )
    assert outcome.engine == "silero"


def test_all_engines_failing_reports_every_reason(tmp_path):
    engines = {
        "edge": FakeEngine("edge", fails=True),
        "silero": FakeEngine("silero", available=False),
    }
    with pytest.raises(base.TtsUnavailable) as info:
        base.synthesize_with_fallback(
            engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
        )
    message = str(info.value)
    assert "Edge" in message and "Silero" in message, "нужно видеть, что случилось с каждым"


def test_no_engines_at_all(tmp_path):
    with pytest.raises(base.TtsUnavailable):
        base.synthesize_with_fallback({}, ["edge"], "привет", {}, 0, 0, tmp_path / "out")


def test_empty_text_rejected_before_any_engine(tmp_path):
    engine = FakeEngine("edge")
    with pytest.raises(base.TtsError):
        base.synthesize_with_fallback(
            {"edge": engine}, ["edge"], "   ", _voices(), 0, 0, tmp_path / "out"
        )
    assert engine.calls == 0


def test_missing_engine_in_registry_is_skipped(tmp_path):
    engines = {"silero": FakeEngine("silero")}
    outcome = base.synthesize_with_fallback(
        engines, ["edge", "silero"], "привет", _voices(), 0, 0, tmp_path / "out"
    )
    assert outcome.engine == "silero"


def test_voice_str_shows_license():
    assert "CC0" in str(base.Voice("id", "Денис", "CC0"))
    assert str(base.Voice("id", "Денис")) == "Денис"
