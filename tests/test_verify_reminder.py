"""Тесты хука-напоминания перед коммитом.

Проверяем две вещи: какие команды хук обязан узнать, и что он никогда не
падает и не шумит на всём остальном. Хук вмешивается в каждый вызов
оболочки, поэтому цена ошибки здесь выше, чем у обычного скрипта: молчащий
хук бесполезен, а болтливый — мешает.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.verify_reminder import TRIGGERS

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_reminder.py"


def run_hook(payload: str) -> subprocess.CompletedProcess[str]:
    """Прогоняет скрипт так же, как это делает Claude Code: JSON на stdin."""
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'fix'",
        "git commit",
        "git commit --amend --no-edit",
        # Инструмент подталкивает не использовать cd, а естественная замена —
        # именно эти формы, поэтому они обязаны ловиться
        "git -C D:/proj commit -m x",
        "git --no-pager commit",
        "git --git-dir=.git commit -m x",
        "cd /tmp && git commit -m x",
        "gh pr create --base main",
        "gh   pr   create",
        "gh pr merge 31 --squash --delete-branch",
    ],
)
def test_reminder_fires(command: str) -> None:
    assert TRIGGERS.search(command), f"не узнал команду: {command}"


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "just all",
        "git status --short",
        "git log --oneline -5",
        "git switch -c f1-process",
        "gh pr list",
        "gh pr view 3",
        "gh run list",
        # Границы слов: похожие, но другие команды
        "git commitx",
        "mygit commit",
    ],
)
def test_reminder_stays_silent(command: str) -> None:
    assert not TRIGGERS.search(command), f"ложное срабатывание: {command}"


def test_payload_gives_reminder() -> None:
    result = run_hook(json.dumps({"tool_input": {"command": "git commit -m x"}}))
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    output = payload["hookSpecificOutput"]
    assert output["hookEventName"] == "PreToolUse"
    assert "verification-before-completion" in output["additionalContext"]


def test_output_is_pure_ascii() -> None:
    """Вывод уходит в канал, где кодировка cp1251, а не UTF-8.

    Экранирование \\uXXXX снимает вопрос кодировки целиком — этот тест
    сторожит решение, чтобы его не «упростили» обратно.
    """
    result = run_hook(json.dumps({"tool_input": {"command": "git commit"}}))
    assert result.stdout.isascii()


@pytest.mark.parametrize(
    "payload",
    [
        "",
        "совсем не json",
        "[]",
        '"строка вместо объекта"',
        "123",
        "null",
        "{}",
        '{"tool_input": null}',
        '{"tool_input": {"command": 42}}',
        # Словарь вместо строки: str() от него содержит нужную подстроку,
        # и наивная проверка выдала бы напоминание на пустом месте
        '{"tool_input": {"command": {"a": "git commit"}}}',
    ],
)
def test_junk_input_is_silent(payload: str) -> None:
    result = run_hook(payload)
    assert result.returncode == 0, f"ненулевой код на входе {payload!r}"
    assert result.stdout.strip() == "", f"лишний вывод на входе {payload!r}"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("git switch -c f1-lefthook", "brainstorming"),
        ("git checkout -b fix-encoding", "brainstorming"),
        ("git commit -m 'x'", "verification-before-completion"),
        ("gh pr create --base main", "requesting-code-review"),
        ("gh pr merge 44 --squash", "IDEAS.md"),
    ],
)
def test_reminder_matches_moment(command: str, expected: str) -> None:
    """Каждый момент получает своё напоминание, а не общее."""
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    assert expected in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_first_moment_wins_on_two_triggers_in_one_command() -> None:
    """`git switch -c x && git commit` — оба триггера в одной строке.

    Порядок шаблонов задан явно (от начала этапа к его закрытию), поэтому
    выигрывает более ранний по смыслу момент — начало ветки, а не коммит.
    """
    command = "git switch -c x && git commit"
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "brainstorming" in context
    assert "verification-before-completion" not in context
