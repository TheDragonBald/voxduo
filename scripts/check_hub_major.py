"""Канарейка: можно ли разрешить huggingface-hub 2 без отката tokenizers.

tokenizers — её тянет faster-whisper, а тот держит tokenizers<1 — требует
huggingface-hub<2.0 (и в 1.0.0rc2 тоже). С hub 2 резолвер откатывает tokenizers на
0.13.3 из 2023 года: тогда она ещё не зависела от hub, зато колёс под Python 3.13 у неё
нет, и сборка падает (PR #59, 9 октября 2026). Поэтому Dependabot не предлагает
мажорные версии hub — правило ignore в .github/dependabot.yml.

Раз в неделю скрипт спрашивает резолвер: наши базовые зависимости, но с
huggingface-hub>=2,<3 — какую tokenizers он выберет под Python проекта и Windows. Не
ниже, чем в uv.lock, — пора снимать запрет.

Код возврата 0 — проверка состоялась, ответ в stdout и в $GITHUB_OUTPUT
(ready=true|false). Код 1 — проверка сломалась: прогон краснеет, а не заводит ложный
issue.

Запуск: uv run --no-project --with packaging scripts/check_hub_major.py
"""

import os
import re
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
HUB = "huggingface-hub"
HUB_2 = "huggingface-hub>=2,<3"
WATCHED = "tokenizers"


def requirements_with_hub_2(pyproject_text: str) -> list[str]:
    """Базовые зависимости проекта, где пин huggingface-hub заменён на >=2,<3."""
    deps: list[str] = tomllib.loads(pyproject_text)["project"]["dependencies"]
    result = [HUB_2 if canonicalize_name(Requirement(dep).name) == HUB else dep for dep in deps]
    if HUB_2 not in result:
        raise ValueError("huggingface-hub нет среди зависимостей проекта")
    return result


def locked_version(lock_text: str, name: str) -> Version:
    """Версия пакета в uv.lock."""
    for package in tomllib.loads(lock_text)["package"]:
        if package["name"] == name:
            return Version(package["version"])
    raise ValueError(f"{name} нет в uv.lock")


def resolved_version(compile_output: str, name: str) -> Version | None:
    """Версия пакета в выводе `uv pip compile`; None — пакета в решении нет."""
    match = re.search(rf"^{re.escape(name)}==(\S+)", compile_output, flags=re.MULTILINE)
    return Version(match.group(1)) if match else None


def is_ready(resolved: Version, locked: Version) -> bool:
    """Пора снимать запрет: резолвер не откатывает пакет ниже нашей версии."""
    return resolved >= locked


def report(ready: bool, message: str) -> None:
    """Ответ — в stdout для журнала и в $GITHUB_OUTPUT для следующего шага."""
    print(message)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        # newline="\n": на Windows текстовый режим записал бы \r\n.
        with open(output, "a", encoding="utf-8", newline="\n") as f:
            f.write(f"ready={'true' if ready else 'false'}\n")


def main() -> int:
    # Как в check_edge.py: ответ по-русски, а консоль Windows и чужая локаль UTF-8 могут не
    # уметь — без этого журнал читается кракозябрами или падает на кодировке.
    for stream in (sys.stdout, sys.stderr):
        if stream is not None and hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    requirements = requirements_with_hub_2((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    locked = locked_version((ROOT / "uv.lock").read_text(encoding="utf-8"), WATCHED)
    python = (ROOT / ".python-version").read_text(encoding="utf-8").strip()
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "requirements.in"
        source.write_text("\n".join(requirements) + "\n", encoding="utf-8")
        result = subprocess.run(
            [
                "uv",
                "pip",
                "compile",
                str(source),
                "--python-version",
                python,
                "--python-platform",
                "windows",
                "--no-header",
                "--no-annotate",
                "--quiet",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    if result.returncode != 0:
        # Текст резолвера — в журнал в обоих случаях: «No solution» бывает не только из-за
        # hub 2, и без него задним числом не разобраться.
        print(result.stderr, file=sys.stderr)
        if "No solution found" in result.stderr:
            report(False, "Ещё рано: с huggingface-hub 2 резолвер не находит решения.")
            return 0
        return 1
    resolved = resolved_version(result.stdout, WATCHED)
    if resolved is None:
        print(f"{WATCHED} нет в решении — проверка устарела, разобраться руками", file=sys.stderr)
        return 1
    if is_ready(resolved, locked):
        report(
            True, f"Пора: с huggingface-hub 2 резолвер берёт {WATCHED} {resolved} (у нас {locked})."
        )
    else:
        report(
            False,
            f"Ещё рано: с huggingface-hub 2 {WATCHED} откатилась бы на {resolved} (у нас {locked}).",
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
