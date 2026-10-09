"""Канарейка huggingface-hub 2: логика скрипта, его исходы и сторож пары «запрет — канарейка».

Настоящий `uv pip compile` здесь не зовётся: main() проверяется с подменённым резолвером, а
сеть — запуском руками и самой канарейкой. Скрипт лежит не в пакете, поэтому грузится по пути.
"""

import importlib.util
import re
import subprocess
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


def fake_project(root: Path) -> None:
    """Корень проекта для main(): pyproject, лок и версия Python — из констант выше."""
    (root / "pyproject.toml").write_text(PYPROJECT, encoding="utf-8")
    (root / "uv.lock").write_text(LOCK, encoding="utf-8")
    (root / ".python-version").write_text("3.13\n", encoding="utf-8")


# Сторож пары смотрит только на живые строки: закомментированное правило не действует, а ключ
# hub-major глубже уровня jobs — не джоб.
_HUB_IGNORE = re.compile(
    r"""^[ \t]*-[ \t]*dependency-name:[ \t]*["']?huggingface-hub["']?[ \t]*$""", re.MULTILINE
)
_HUB_JOB = re.compile(r"^  hub-major:[ \t]*$", re.MULTILINE)


def has_hub_ignore(dependabot_text: str) -> bool:
    """Есть ли в dependabot.yml действующее правило ignore для huggingface-hub."""
    return _HUB_IGNORE.search(dependabot_text) is not None


def has_hub_job(canary_text: str) -> bool:
    """Есть ли в canary.yml джоб hub-major."""
    return _HUB_JOB.search(canary_text) is not None


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
    with pytest.raises(ValueError, match="huggingface-hub нет среди зависимостей"):
        hub.requirements_with_hub_2(PYPROJECT.replace('    "huggingface-hub==1.30.0",\n', ""))


def test_locked_version_is_read() -> None:
    assert hub.locked_version(LOCK, "tokenizers") == Version("0.23.2")


def test_locked_version_missing_is_an_error() -> None:
    with pytest.raises(ValueError, match="nope нет в uv.lock"):
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


@pytest.mark.parametrize(("ready", "line"), [(True, b"ready=true\n"), (False, b"ready=false\n")])
def test_report_writes_ready_to_github_output(
    ready: bool,
    line: bytes,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    hub.report(ready, "ответ канарейки")
    # Байты, а не текст: так видно и лишний \r на Windows.
    assert output.read_bytes() == line
    assert "ответ канарейки" in capsys.readouterr().out


def test_report_without_github_output_only_prints(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # Запуск руками: переменной нет, ответ только в stdout.
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    hub.report(True, "ответ канарейки")
    assert "ответ канарейки" in capsys.readouterr().out


@pytest.mark.parametrize(
    ("returncode", "stdout", "stderr", "code", "written"),
    [
        (0, "faster-whisper==1.2.1\ntokenizers==0.13.3\n", "", 0, b"ready=false\n"),
        (0, "tokenizers==0.23.3\n", "", 0, b"ready=true\n"),
        (1, "", "  × No solution found when resolving dependencies:\n", 0, b"ready=false\n"),
        (2, "", "error: Failed to fetch: `https://pypi.org/simple/tokenizers/`\n", 1, None),
        (0, "faster-whisper==1.2.1\n", "", 1, None),
    ],
    ids=["rollback", "ready", "no-solution", "broken", "no-tokenizers"],
)
def test_main_outcomes(
    returncode: int,
    stdout: str,
    stderr: str,
    code: int,
    written: bytes | None,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_project(tmp_path)
    monkeypatch.setattr(hub, "ROOT", tmp_path)
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(
        hub.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, returncode, stdout, stderr),
    )
    assert hub.main() == code
    if written is None:
        # Сломанная проверка не пишет ready вовсе — шаг с issue не запустится.
        assert not output.exists()
    else:
        assert output.read_bytes() == written


@pytest.mark.parametrize(
    ("returncode", "stderr", "code"),
    [
        (1, "  × No solution found when resolving dependencies:\n  ╰─▶ причина\n", 0),
        (2, "error: Failed to fetch: `https://pypi.org/simple/tokenizers/`\n", 1),
    ],
    ids=["no-solution", "broken"],
)
def test_main_keeps_resolver_reason_in_log(
    returncode: int,
    stderr: str,
    code: int,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # «No solution» бывает не только из-за hub 2 — без текста резолвера задним числом не разобраться.
    fake_project(tmp_path)
    monkeypatch.setattr(hub, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output"))
    monkeypatch.setattr(
        hub.subprocess,
        "run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, returncode, "", stderr),
    )
    assert hub.main() == code
    assert stderr.strip() in capsys.readouterr().err


def test_main_asks_resolver_about_hub_2_on_windows(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake_project(tmp_path)
    monkeypatch.setattr(hub, "ROOT", tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(tmp_path / "github_output"))
    seen: dict[str, list[str]] = {}

    def fake_run(args: list[str], **kwargs: object) -> subprocess.CompletedProcess[str]:
        seen["args"] = args
        # Файл требований живёт только на время вызова — читаем его здесь.
        source = next(arg for arg in args if arg.endswith("requirements.in"))
        seen["requirements"] = Path(source).read_text(encoding="utf-8").splitlines()
        return subprocess.CompletedProcess(args, 0, "tokenizers==0.13.3\n", "")

    monkeypatch.setattr(hub.subprocess, "run", fake_run)
    assert hub.main() == 0
    args = seen["args"]
    assert args[:3] == ["uv", "pip", "compile"]
    assert args[args.index("--python-version") + 1] == "3.13"
    assert args[args.index("--python-platform") + 1] == "windows"
    assert seen["requirements"] == [
        "faster-whisper==1.2.1",
        "huggingface-hub>=2,<3",
        "piper-tts==1.3.0",
    ]


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('      - dependency-name: "huggingface-hub"\n', True),
        ("      - dependency-name: huggingface-hub\n", True),
        ('      # - dependency-name: "huggingface-hub"\n', False),
        ('      - dependency-name: "huggingface-hub-extra"\n', False),
        ('      - dependency-name: "torch"\n', False),
    ],
    ids=["quoted", "bare", "commented", "longer-name", "other-package"],
)
def test_hub_ignore_detection(text: str, expected: bool) -> None:
    assert has_hub_ignore(text) is expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("jobs:\n  hub-major:\n    runs-on: ubuntu-latest\n", True),
        ("jobs:\n  # hub-major:\n", False),
        ("jobs:\n  check:\n    hub-major:\n", False),
        ("jobs:\n  check:\n", False),
    ],
    ids=["job", "commented", "nested-key", "absent"],
)
def test_hub_job_detection(text: str, expected: bool) -> None:
    assert has_hub_job(text) is expected


def test_hub_ignore_and_canary_job_live_together() -> None:
    # Запрет без канарейки забудется навсегда, канарейка без запрета — пустой шум.
    dependabot = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    canary = (ROOT / ".github" / "workflows" / "canary.yml").read_text(encoding="utf-8")
    assert has_hub_ignore(dependabot) == has_hub_job(canary), (
        "запрет мажора huggingface-hub в dependabot.yml и джоб hub-major в canary.yml "
        "живут и удаляются вместе"
    )
