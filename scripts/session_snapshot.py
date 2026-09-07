"""Снимок состояния проекта на диск.

Запускается хуком PreCompact — прямо перед тем, как контекст сессии будет
сжат. Смысл в том, чтобы после сжатия можно было восстановить не пересказ
модели, а факты: где мы находимся в git и что не закрыто в плане.

Собирает только детерминированные данные. Ничего не интерпретирует — именно
поэтому снимку можно верить, в отличие от сгенерированного резюме.

Запуск вручную: uv run python scripts/session_snapshot.py
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT = ROOT / ".claude" / "session-state.md"

# Сколько незакрытых пунктов плана показывать: больше — это уже чтение плана,
# а не напоминание о нём
MAX_OPEN_ITEMS = 12


def git(*args: str) -> str:
    """Выполняет команду git, возвращая пустую строку при любой неудаче."""
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def open_plan_items() -> list[str]:
    """Неотмеченные пункты из локального плана, если он есть."""
    plan = ROOT / "PLAN.md"
    if not plan.exists():
        return []
    try:
        lines = plan.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []

    items: list[str] = []
    section = ""
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("### "):
            section = stripped[4:]
        elif stripped.startswith("- [ ]"):
            text = stripped[5:].strip()
            items.append(f"{section} — {text}" if section else text)
    return items


def main() -> int:
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")

    branch = git("rev-parse", "--abbrev-ref", "HEAD") or "?"
    commits = git("log", "--oneline", "-5") or "история недоступна"
    status = git("status", "--short")
    remote = git("status", "-sb").splitlines()[:1]

    items = open_plan_items()
    shown = items[:MAX_OPEN_ITEMS]

    parts = [
        "# Снимок состояния сессии",
        "",
        "Записан автоматически перед сжатием контекста. Только факты из git и",
        "плана — ничего пересказанного. Полный контекст: `CLAUDE.md`,",
        "`PLAN.md`, `IDEAS.md`.",
        "",
        f"Время: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## Git",
        "",
        f"Ветка: `{branch}`",
    ]
    if remote:
        parts.append(f"Синхронизация: `{remote[0]}`")

    parts += ["", "Последние коммиты:", "", "```", commits, "```", ""]

    if status:
        parts += ["Незакоммиченные изменения:", "", "```", status, "```", ""]
    else:
        parts += ["Рабочее дерево чистое.", ""]

    parts += ["## Незакрытые пункты плана", ""]
    if shown:
        parts += [f"- {item}" for item in shown]
        if len(items) > len(shown):
            parts.append(f"- …и ещё {len(items) - len(shown)}, целиком в `PLAN.md`")
    else:
        parts.append("Не найдено — либо всё закрыто, либо `PLAN.md` отсутствует.")

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
    print(f"Снимок сохранён: {OUTPUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
