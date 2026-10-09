"""Сторож связки «faster-whisper + av»: декодирование файла и срок запрета av 19.

PyAV 19 убрал аргумент metadata_errors у av.open, а faster-whisper версии HELD_FOR
его передаёт: decode_audio падает с TypeError на любом файле (опыт 9 октября 2026,
PR #64). CI этого не видел: ни один тест не декодировал файл, а оба пакета
импортируются лениво. Upstream починил (SYSTRAN/faster-whisper#1495), но в релиз
HELD_FOR починка не вошла, поэтому мажор av придержан в .github/dependabot.yml.

Модели и сеть не нужны: декодируется секунда синуса, записанная модулем wave.
"""

import math
import re
import struct
import wave
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SAMPLE_RATE = 16_000
# Версия faster-whisper, из-за которой придержан мажор av. Сдвинулась — пора
# проверить, вошла ли в релиз починка #1495, и снять запрет.
HELD_FOR = "1.2.1"

# Только живые строки: закомментированное правило не действует.
_AV_IGNORE = re.compile(
    r"""^[ \t]*-[ \t]*dependency-name:[ \t]*["']?av["']?[ \t]*$""", re.MULTILINE
)
_FASTER_WHISPER_PIN = re.compile(r'"faster-whisper==([^"]+)"')


@pytest.fixture
def tone(tmp_path: Path) -> Path:
    """Секунда синуса 440 Гц: 16 кГц, моно, 16 бит."""
    path = tmp_path / "tone.wav"
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(
            b"".join(
                struct.pack("<h", int(8000 * math.sin(2 * math.pi * 440 * i / SAMPLE_RATE)))
                for i in range(SAMPLE_RATE)
            )
        )
    return path


def test_faster_whisper_decodes_file(tone: Path) -> None:
    from faster_whisper import decode_audio

    audio = decode_audio(str(tone))
    assert audio.dtype == np.float32
    assert audio.shape == (SAMPLE_RATE,)


def test_player_fallback_decodes_file(tone: Path) -> None:
    from voxduo.tts.player import _read_with_av

    data, rate = _read_with_av(tone)
    assert rate == SAMPLE_RATE
    assert data.shape == (SAMPLE_RATE,)


def av_hold_outdated(pyproject_text: str, dependabot_text: str) -> bool:
    """Запрет мажора av стоит, а faster-whisper уже не та версия, из-за которой он стоит."""
    pin = _FASTER_WHISPER_PIN.search(pyproject_text)
    if pin is None:
        raise ValueError("пин faster-whisper не найден в pyproject.toml")
    return _AV_IGNORE.search(dependabot_text) is not None and pin.group(1) != HELD_FOR


HOLD = (
    "    ignore:\n"
    '      - dependency-name: "av"\n'
    '        update-types: ["version-update:semver-major"]\n'
)
# Любая версия, кроме HELD_FOR: случаи ниже не завязаны на номер и переживают его подъём.
NEWER = f"{HELD_FOR}.post1"


@pytest.mark.parametrize(
    ("pin", "dependabot", "outdated"),
    [
        (HELD_FOR, HOLD, False),  # запрет стоит по делу
        (NEWER, HOLD, True),  # faster-whisper сдвинулся — пора пересмотреть
        (NEWER, HOLD.replace('"av"', "av"), True),  # имя без кавычек — тот же запрет
        (NEWER, "", False),  # запрет уже снят
        (NEWER, HOLD.replace("- dependency-name", "# - dependency-name"), False),
        (NEWER, HOLD.replace('"av"', '"avro"'), False),  # другое имя
    ],
    ids=["pin-is-held-for", "moved-on", "unquoted-name", "lifted", "commented-out", "other-name"],
)
def test_av_hold_outdated(pin: str, dependabot: str, outdated: bool) -> None:
    pyproject = f'dependencies = [\n    "faster-whisper=={pin}",\n]\n'
    assert av_hold_outdated(pyproject, dependabot) is outdated


def test_av_hold_outdated_without_pin_is_an_error() -> None:
    with pytest.raises(ValueError, match="faster-whisper"):
        av_hold_outdated("dependencies = []\n", HOLD)


def test_av_hold_is_still_justified() -> None:
    # Красный здесь — не поломка, а напоминание: бот принёс faster-whisper новее
    # HELD_FOR, а мажор av всё ещё придержан. Проверить, вошла ли в релиз починка
    # SYSTRAN/faster-whisper#1495. Да — удалить запись av из ignore в
    # .github/dependabot.yml, комментарий о запрете у пина av в pyproject.toml и весь
    # сторож срока в этом файле: HELD_FOR, NEWER, HOLD, _AV_IGNORE, _FASTER_WHISPER_PIN,
    # av_hold_outdated и три его теста, а с ними ставшие лишними ROOT и import re;
    # докстринг модуля переписать под оставшиеся тесты декодирования. Нет — поднять
    # HELD_FOR до новой версии и номер версии в комментариях о запрете
    # (.github/dependabot.yml, pyproject.toml).
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    # Результат — в переменную: иначе на красном pytest напечатает куски обоих файлов.
    outdated = av_hold_outdated(pyproject, dependabot)
    assert not outdated, (
        "faster-whisper обновлён, а мажор av всё ещё придержан — пересмотреть запрет"
    )
