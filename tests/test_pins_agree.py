"""Сверка версий, продублированных вне `pyproject.toml`.

Точка истины для версий — `pyproject.toml` и `uv.lock`. Но канарейка ставит
`edge-tts` отдельной командой `uv run --no-project --with ...`: полное окружение
ей не нужно, а `--with` требует версию прямо в строке.

Дубль опасен тем, что расходится молча. Dependabot поднимет пин в
`pyproject.toml`, до `canary.yml` не дотянется — и канарейка неделями будет
проверять версию, которой нет ни у одного пользователя, то есть промолчит
ровно тогда, когда сломано у всех.

Второй такой дубль — версия Python: она названа в `.python-version`, в
`requires-python`, в `[tool.mypy].python_version` и в `[tool.ruff].target-version`.
Разъехавшись, они дадут проверку кода под одну версию при запуске на другой.

Третий дубль — версия lefthook: пин `lefthook==X.Y.Z` в dev-группе
`pyproject.toml` и `min_version` в `lefthook.yml`. Разъехавшись, Dependabot
поднимет пин зависимости, а `min_version` соврёт про то, какой lefthook
на самом деле нужен.

Четвёртый дубль — нижняя граница версии uv: `required-version` в
`[tool.uv]` и `$minUv` в `install.ps1`. Разъехавшись, они дадут установку,
которая обрывается на окружении, объявленном достаточным: скрипт потребует
версию выше и выйдет с кодом 1, хотя проект с ней работает. Граница вдобавок
привязана к внешнему факту — Dependabot запускает свой uv, и поднимать её без
проверки нельзя, — так что расходиться этим двоим особенно нежелательно.

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
PYTHON_VERSION = ROOT / ".python-version"
LEFTHOOK_YML = ROOT / "lefthook.yml"
INSTALL_PS1 = ROOT / "install.ps1"

# Версия внутри --with "edge-tts==X.Y.Z"
_CANARY_PIN = re.compile(r'--with\s+"edge-tts==([^"]+)"')

# Версия внутри min_version: "X.Y.Z"
_MIN_VERSION = re.compile(r'^min_version:\s*"([^"]+)"', re.MULTILINE)

# Версия внутри $minUv = [version]'X.Y.Z'
_MIN_UV = re.compile(r"\$minUv\s*=\s*\[version\]'([^']+)'")

# Нижняя граница внутри required-version = ">=X.Y.Z"
_REQUIRED_UV = re.compile(r'required-version\s*=\s*">=([^"]+)"')


def canary_pin(text: str) -> str | None:
    """Версия edge-tts, которую ставит канарейка, или None."""
    match = _CANARY_PIN.search(text)
    return match.group(1) if match else None


def min_version_pin(text: str) -> str | None:
    """Версия lefthook из min_version в lefthook.yml, или None."""
    match = _MIN_VERSION.search(text)
    return match.group(1) if match else None


def min_uv_in_installer(text: str) -> str | None:
    """Нижняя граница uv из install.ps1, или None."""
    match = _MIN_UV.search(text)
    return match.group(1) if match else None


def required_uv(text: str) -> str | None:
    """Нижняя граница uv из required-version в pyproject.toml, или None."""
    match = _REQUIRED_UV.search(text)
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


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('min_version: "2.1.12"', "2.1.12"),
        ('min_version: "2.1.12"\npre-commit:\n  piped: true', "2.1.12"),
        ("min_version: 2.1.12", None),  # без кавычек — не наш формат
        ("ничего похожего", None),
    ],
)
def test_min_version_pin_parsing(text: str, expected: str | None) -> None:
    assert min_version_pin(text) == expected


def test_lefthook_pin_agrees_with_min_version() -> None:
    """Пин lefthook в pyproject.toml и min_version в lefthook.yml — одно и то же."""
    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    declared = declared_pin(config["dependency-groups"]["dev"], "lefthook")
    assert declared is not None, "lefthook пропал из dev-группы зависимостей"

    in_lefthook_yml = min_version_pin(LEFTHOOK_YML.read_text(encoding="utf-8"))
    assert in_lefthook_yml is not None, "в lefthook.yml не нашлось min_version"

    assert in_lefthook_yml == declared, (
        f"lefthook.yml требует минимум {in_lefthook_yml}, а в pyproject.toml "
        f"закреплён {declared}. Подняли пин в одном месте — поднимите и в другом"
    )


def test_python_version_agrees_everywhere() -> None:
    """Версия Python названа в четырёх местах — все должны говорить одно."""
    declared = PYTHON_VERSION.read_text(encoding="utf-8").strip()
    assert declared, ".python-version пуст"

    config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))

    mypy_version = config["tool"]["mypy"]["python_version"]
    assert mypy_version == declared, (
        f"mypy проверяет код под Python {mypy_version}, а запускается он на {declared}"
    )

    # ruff записывает версию иначе: py313 вместо 3.13
    ruff_target = config["tool"]["ruff"]["target-version"]
    assert ruff_target == "py" + declared.replace(".", ""), (
        f"ruff настроен на {ruff_target}, а Python в проекте {declared}"
    )

    requires = config["project"]["requires-python"]
    major, minor = declared.split(".")[:2]
    assert f">={major}.{minor}" in requires, (
        f"requires-python = {requires} не согласуется с .python-version = {declared}"
    )


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("$minUv = [version]'0.12.7'", "0.12.7"),
        ("$minUv  =  [version]'1.0.0'\nWrite-Host x", "1.0.0"),
        ("$minUv = '0.12.7'", None),  # без [version] — не наш формат
        ("ничего похожего", None),
    ],
)
def test_min_uv_parsing(text: str, expected: str | None) -> None:
    assert min_uv_in_installer(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ('required-version = ">=0.12.7"', "0.12.7"),
        ('[tool.uv]\nrequired-version = ">=1.2.3"\npackage = false', "1.2.3"),
        ('required-version = "==0.12.7"', None),  # не нижняя граница
        ("ничего похожего", None),
    ],
)
def test_required_uv_parsing(text: str, expected: str | None) -> None:
    assert required_uv(text) == expected


def test_installer_uv_floor_agrees_with_pyproject() -> None:
    """Нижняя граница uv названа дважды — в pyproject.toml и в install.ps1.

    Расхождение видно не сразу: `just all` и CI останутся зелёными, потому что
    здешний uv свежее обеих границ. Сломается установка у человека с версией
    между ними — скрипт объявит её недостаточной и выйдет с кодом 1, хотя
    проект с ней работает.
    """
    declared = required_uv(PYPROJECT.read_text(encoding="utf-8"))
    assert declared is not None, "в pyproject.toml не нашлось required-version с >="

    # install.ps1 хранится в UTF-8 с BOM: Windows PowerShell 5.1 без BOM читает
    # файл в ANSI и портит кириллицу.
    in_installer = min_uv_in_installer(INSTALL_PS1.read_text(encoding="utf-8-sig"))
    assert in_installer is not None, "в install.ps1 не нашлась переменная $minUv"

    assert in_installer == declared, (
        f"install.ps1 требует uv {in_installer}, а pyproject.toml — {declared}. "
        f"Подняли границу в одном месте — поднимите и в другом"
    )
