"""Сверка версий, продублированных вне `pyproject.toml`.

Точка истины для версий — `pyproject.toml` и `uv.lock`. Но канарейка ставит
`edge-tts` отдельной командой `uv run --no-project --with ...`: полное окружение
ей не нужно, а `--with` требует версию прямо в строке.

Дубль опасен тем, что расходится молча. Dependabot поднимет пин в
`pyproject.toml`, до `canary.yml` не дотянется — и канарейка неделями будет
проверять версию, которой нет ни у одного пользователя, то есть промолчит
ровно тогда, когда сломано у всех.

Тест краснеет в CI при первом же расхождении.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CANARY = ROOT / ".github" / "workflows" / "canary.yml"
PYPROJECT = ROOT / "pyproject.toml"

# Версия внутри --with "edge-tts==X.Y.Z"
_CANARY_PIN = re.compile(r'--with\s+"edge-tts==([^"]+)"')


def canary_pin(text: str) -> str | None:
    """Версия edge-tts, которую ставит канарейка, или None."""
    match = _CANARY_PIN.search(text)
    return match.group(1) if match else None


def declared_pin(dependencies: list[str], name: str) -> str | None:
    """Версия пакета из списка зависимостей проекта, или None."""
    for entry in dependencies:
        left, sep, right = entry.partition("==")
        if sep and left.strip() == name:
            return right.strip()
    return None


def test_canary_pin_matches_pyproject() -> None:
    """Канарейка проверяет ту же версию edge-tts, что стоит у пользователей."""
    declared = declared_pin(
        tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))["project"]["dependencies"],
        "edge-tts",
    )
    assert declared is not None, "edge-tts пропал из зависимостей проекта"

    in_canary = canary_pin(CANARY.read_text(encoding="utf-8"))
    assert in_canary is not None, (
        'в canary.yml не нашлось строки --with "edge-tts==...". '
        "Если канарейку перевели на uv sync, этот тест можно удалить: "
        "дубля версии больше нет."
    )

    assert in_canary == declared, (
        f"канарейка ставит edge-tts=={in_canary}, а у пользователей {declared}. "
        f"Поднимая версию в pyproject.toml, поднимите и в .github/workflows/canary.yml"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('run: uv run --no-project --with "edge-tts==7.2.8" scripts/check_edge.py', "7.2.8"),
        ('--with "edge-tts==1.0.0rc1"', "1.0.0rc1"),
        ("--with edge-tts", None),  # без версии — не пин
        ("ничего похожего", None),
    ],
)
def test_canary_pin_parsing(text: str, expected: str | None) -> None:
    assert canary_pin(text) == expected


@pytest.mark.parametrize(
    ("deps", "name", "expected"),
    [
        (["edge-tts==7.2.8"], "edge-tts", "7.2.8"),
        (["numpy==2.5.3", "edge-tts==7.2.8"], "edge-tts", "7.2.8"),
        (["edge-tts>=7.0"], "edge-tts", None),  # не точный пин
        (["edge-tts-extra==1.0"], "edge-tts", None),  # похожее имя не считается
        ([], "edge-tts", None),
    ],
)
def test_declared_pin_parsing(deps: list[str], name: str, expected: str | None) -> None:
    assert declared_pin(deps, name) == expected
