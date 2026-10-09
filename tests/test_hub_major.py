"""Канарейка huggingface-hub 2: чистая логика скрипта и сторож пары «запрет — канарейка».

Сетевой прогон `uv pip compile` здесь не тестируется: его проверяют запуск руками и сама
канарейка. Скрипт лежит не в пакете, поэтому грузится по пути.
"""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "check_hub_major.py"


def load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_hub_major", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


hub = load_script()

PYPROJECT = """
[project]
name = "demo"
dependencies = [
    "faster-whisper==1.2.1",
    "huggingface-hub==1.30.0",
    "piper-tts==1.3.0",
]
"""

LOCK = """
version = 1

[[package]]
name = "tokenizers"
version = "0.23.2"

[[package]]
name = "torch"
version = "2.14.1+cpu"
"""


def test_hub_pin_is_lifted_to_2() -> None:
    assert hub.requirements_with_hub_2(PYPROJECT) == [
        "faster-whisper==1.2.1",
        "huggingface-hub>=2,<3",
        "piper-tts==1.3.0",
    ]


def test_hub_name_is_matched_canonically() -> None:
    text = PYPROJECT.replace("huggingface-hub==1.30.0", "Huggingface_Hub==1.30.0")
    assert "huggingface-hub>=2,<3" in hub.requirements_with_hub_2(text)


def test_missing_hub_is_an_error() -> None:
    with pytest.raises(ValueError):
        hub.requirements_with_hub_2(PYPROJECT.replace('    "huggingface-hub==1.30.0",\n', ""))


def test_locked_version_is_read() -> None:
    assert hub.locked_version(LOCK, "tokenizers") == Version("0.23.2")


def test_locked_version_missing_is_an_error() -> None:
    with pytest.raises(ValueError):
        hub.locked_version(LOCK, "nope")


@pytest.mark.parametrize(
    ("output", "expected"),
    [
        ("faster-whisper==1.2.1\ntokenizers==0.13.3\n", Version("0.13.3")),
        ("tokenizers==0.23.3 ; sys_platform == 'win32'\n", Version("0.23.3")),
        ("faster-whisper==1.2.1\n", None),
        ("my-tokenizers==9.9\n", None),
    ],
)
def test_resolved_version(output: str, expected: Version | None) -> None:
    assert hub.resolved_version(output, "tokenizers") == expected


@pytest.mark.parametrize(
    ("resolved", "ready"),
    [
        ("0.13.3", False),  # откат, как в PR #59 9 октября
        ("0.23.2", True),  # та же версия — hub 2 её устроил
        ("0.23.3", True),
        ("1.0.0rc2", True),
    ],
)
def test_is_ready(resolved: str, ready: bool) -> None:
    assert hub.is_ready(Version(resolved), Version("0.23.2")) is ready


def test_hub_ignore_and_canary_job_live_together() -> None:
    # Запрет без канарейки забудется навсегда, канарейка без запрета — пустой шум.
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    canary = (ROOT / ".github" / "workflows" / "canary.yml").read_text(encoding="utf-8")
    has_ignore = 'dependency-name: "huggingface-hub"' in dependabot
    has_job = "scripts/check_hub_major.py" in canary
    assert has_ignore == has_job, (
        "запрет мажора huggingface-hub в dependabot.yml и джоб hub-major в canary.yml "
        "живут и удаляются вместе"
    )
