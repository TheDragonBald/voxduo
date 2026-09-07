# Команды проекта VoxDuo.
# Запуск: just <команда>. Без аргументов — список всех команд.
#
# Всё идёт через .venv, а не через python из PATH: в PATH здесь Python 3.14
# без пакетов, и запуск оттуда падает с невнятной ошибкой импорта.

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

# Проверить стиль
lint:
    {{ python }} -m ruff check .

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
    explorer.exe "$LOCALAPPDATA/VoxDuo/logs"

# Убрать временные файлы сборки и кэши
clean:
    -rm -rf build dist .pytest_cache .ruff_cache htmlcov .coverage
    -find . -type d -name __pycache__ -exec rm -rf {} +
