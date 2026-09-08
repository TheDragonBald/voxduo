# Команды проекта VoxDuo.
# Запуск: just <команда>. Без аргументов — список всех команд.
#
# Всё идёт через .venv, а не через python из PATH: в PATH здесь Python 3.14
# без пакетов, и запуск оттуда падает с невнятной ошибкой импорта.

# just на Windows по умолчанию ищет оболочку sh. Она в системе есть —
# C:\Program Files\Git\usr\bin\sh.exe, — но Git намеренно не добавляет этот
# каталог в PATH, чтобы юниксовые утилиты не перекрывали команды Windows.
# Поэтому из PowerShell just падал с «could not find the shell `sh`».
# PowerShell есть на любой Windows и не требует ничего доустанавливать.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

python := ".venv/Scripts/python.exe"

# Показать список команд
default:
    @just --list --unsorted

# --- установка ---

# Создать окружение и поставить базовые зависимости
install:
    py -3.13 -m venv .venv
    {{ python }} -m pip install -U pip
    {{ python }} -m pip install -r requirements.txt

# Доставить поддержку видеокарты NVIDIA (~1 ГБ)
install-gpu:
    {{ python }} -m pip install -r requirements-gpu.txt

# Доставить движок синтеза Silero, ему нужен torch (~250 МБ)
install-silero:
    {{ python }} -m pip install -r requirements-silero.txt

# Доставить инструменты разработки
install-dev:
    {{ python }} -m pip install -r requirements-dev.txt

# Полная установка: всё сразу
install-all: install install-gpu install-silero install-dev

# --- запуск ---

# Запустить приложение
run:
    {{ python }} -m voxduo

# Запустить с подробными логами (в лог попадают и тексты)
debug:
    {{ python }} -m voxduo --debug

# Показать сводку об окружении: версии, видеокарта, пути
check:
    {{ python }} -m voxduo --check

# --- проверки ---

# Прогнать тесты
test:
    {{ python }} -m pytest

# Тесты с отчётом о покрытии
cov:
    {{ python }} -m pytest --cov=voxduo --cov-report=term-missing

# Проверить стиль и форматирование
#
# Обе команды отдельными строками: just обрывает рецепт на первой же
# неудаче, поэтому упавший линтер не спрячется за успешным форматтером.
# Форматирование проверяется и здесь, и в CI — иначе «у меня зелено»
# перестаёт означать «в CI зелено», а именно это расхождение мы и лечим.
lint:
    {{ python }} -m ruff check .
    {{ python }} -m ruff format --check .

# Отформатировать и починить, что чинится автоматически
fmt:
    {{ python }} -m ruff format .
    {{ python }} -m ruff check --fix .

# Всё, что стоит прогнать перед коммитом
all: lint test

# Прогон движков синтеза вживую: сеть, модели, звук
smoke:
    {{ python }} scripts/smoke.py

# То же, но с воспроизведением результата
smoke-play:
    {{ python }} scripts/smoke.py --play

# --- сборка и обслуживание ---

# Собрать voxduo.exe
build:
    {{ python }} -m PyInstaller voxduo.spec --noconfirm

# Открыть папку с логами
logs:
    explorer.exe "$env:LOCALAPPDATA\VoxDuo\logs"

# Убрать временные файлы сборки и кэши
#
# Проверяем существование перед удалением, а не глушим ошибки через
# -ErrorAction SilentlyContinue: тот прячет сообщение, но рецепт всё равно
# завершается с кодом 1, и следующая строка не выполняется.
# Кэши ищем только в своих папках — внутри .venv их под тысячу.
clean:
    foreach ($p in 'build','dist','.pytest_cache','.ruff_cache','htmlcov','.coverage') { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
    foreach ($d in 'voxduo','tests','scripts') { if (Test-Path $d) { Get-ChildItem $d -Recurse -Directory -Filter __pycache__ | ForEach-Object { Remove-Item -Recurse -Force $_.FullName } } }
