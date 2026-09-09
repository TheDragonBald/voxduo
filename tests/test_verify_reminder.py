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

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "verify_reminder.py"


def run_hook(payload: str) -> subprocess.CompletedProcess[str]:
    """Прогоняет скрипт так же, как это делает Claude Code: JSON на stdin.

    Инвариант проекта — хук PreToolUse никогда не блокирует вызов и всегда
    завершается кодом 0 (блокировка — это код 2). Проверяем его здесь один
    раз, чтобы он покрывал каждый тест файла, а не только те немногие, что
    сами дублировали эту проверку.
    """
    result = subprocess.run(
        [sys.executable, str(SCRIPT)],
        input=payload,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )
    assert result.returncode == 0, f"хук вернул {result.returncode}: {result.stderr}"
    return result


@pytest.mark.parametrize(
    "command",
    [
        "git commit -m 'fix'",
        "git commit",
        "git commit --amend --no-edit",
        # Историческая граница: инструмент оболочки подталкивает не
        # использовать cd, а естественная замена — именно эти формы. Три
        # настоящих бага стоило найти это правило, проверяем сквозным
        # прогоном хука, а не регулярки напрямую
        "git -C D:/proj commit -m x",
        "git --no-pager commit",
        "git --git-dir=.git commit -m x",
        "cd /tmp && git commit -m x",
    ],
)
def test_hook_fires_commit_reminder(command: str) -> None:
    """Прогон через сам хук: границы `git commit`, а не константа TRIGGERS."""
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "verification-before-completion" in context, f"не узнал команду: {command}"


@pytest.mark.parametrize(
    ("command", "expected"),
    [
        ("gh pr create --base main", "requesting-code-review"),
        ("gh   pr   create", "requesting-code-review"),
        ("gh pr merge 31 --squash --delete-branch", "IDEAS.md"),
    ],
)
def test_hook_fires_pr_reminder(command: str, expected: str) -> None:
    """Прогон через сам хук: gh pr create/merge дают свой текст каждая."""
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert expected in context, f"не узнал команду: {command}"


@pytest.mark.parametrize(
    "command",
    [
        "ls -la",
        "just all",
        "git status --short",
        "git log --oneline -5",
        "gh pr list",
        "gh pr view 3",
        "gh run list",
        # Границы слов: похожие, но другие команды
        "git commitx",
        "mygit commit",
        # Штатный шаг 6 процедуры проекта («Чистка: git switch main →
        # git pull») и обычный откат файла — не начало этапа, молчать обязан
        "git switch main",
        "git checkout main",
        "git checkout -- file.txt",
    ],
)
def test_hook_stays_silent(command: str) -> None:
    """Сквозной прогон хука, а не только regex: пустой stdout и код 0.

    Проверка по регулярке напрямую пропустила бы слишком широкий шаблон —
    ошибиться можно в main(), а не только в самом паттерне.
    """
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    assert result.returncode == 0
    assert result.stdout.strip() == "", f"ложное срабатывание: {command}"


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
        # Штатные формы, которые старый паттерн не ловил: `-C`/`-B` и
        # `--create` перезаписывают существующую ветку, но это тоже начало
        # этапа
        ("git switch -C hotfix", "brainstorming"),
        ("git switch --create hotfix", "brainstorming"),
        ("git checkout -B main", "brainstorming"),
        # Глобальные флаги git перед подкомандой — та же щель, что три раза
        # стоила проекту багов у COMMIT (см. историческую границу ниже)
        ("git -C D:/proj switch -c f1-next", "brainstorming"),
        ("git --no-pager checkout -b fix-x", "brainstorming"),
        ("git commit -m 'x'", "verification-before-completion"),
        ("gh pr create --base main", "requesting-code-review"),
        ("gh pr merge 44 --squash", "IDEAS.md"),
    ],
)
def test_reminder_matches_moment(command: str, expected: str) -> None:
    """Каждый момент получает своё напоминание, а не общее."""
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    assert expected in json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]


def test_leftmost_trigger_wins_on_two_triggers_in_one_command() -> None:
    """`git switch -c x && git commit` — оба триггера в одной строке.

    Побеждает не первый по списку MOMENTS, а тот, что стоит в самой команде
    раньше по позиции. Здесь оба критерия совпадают (branch-start и раньше
    по тексту, и раньше по списку), поэтому тест не отличает их друг от
    друга — за это отвечают три теста ниже на реальные коллизии.
    """
    command = "git switch -c x && git commit"
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "brainstorming" in context
    assert "verification-before-completion" not in context


@pytest.mark.parametrize(
    ("command", "expected", "unexpected"),
    [
        # Сообщение коммита само упоминает git-команду текстом — регрессия,
        # найденная ревью: победил бы BRANCH_START только потому, что он
        # раньше в списке MOMENTS, хотя в самой строке COMMIT стоит раньше
        (
            "git commit -m 'Split hook: see git switch -c example'",
            "verification-before-completion",
            "brainstorming",
        ),
        # Тело PR описывает команду коммита — PR_CREATE должен выиграть,
        # а не COMMIT, встреченный позже в тексте
        (
            "gh pr create --body '...git commit'",
            "requesting-code-review",
            "verification-before-completion",
        ),
        # Мерж и следом реальное начало новой ветки — мерж стоит в команде
        # раньше и должен выиграть, а не BRANCH_START
        (
            "gh pr merge 44 --squash && git switch -c f1-next",
            "IDEAS.md",
            "brainstorming",
        ),
    ],
)
def test_leftmost_position_wins_on_real_collision(
    command: str, expected: str, unexpected: str
) -> None:
    """Выбор идёт по самой левой позиции совпадения, а не по порядку MOMENTS.

    Доказано регрессией: до этого исправления первая из трёх команд отдавала
    напоминание про начало этапа вместо verification-before-completion,
    хотя команда — это `git commit`, а `git switch -c` — просто текст внутри
    сообщения коммита.
    """
    result = run_hook(json.dumps({"tool_input": {"command": command}}))
    context = json.loads(result.stdout)["hookSpecificOutput"]["additionalContext"]
    assert expected in context, f"{command!r}: ожидали {expected!r}, получили {context!r}"
    assert unexpected not in context, f"{command!r}: неожиданно нашли {unexpected!r}"
