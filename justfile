# Команды проекта VoxDuo.
# Запуск: just <команда>. Без аргументов — список всех команд.
#
# Всё идёт через uv: он держит .venv в соответствии с uv.lock, а python из PATH
# здесь — 3.14 без пакетов, и запуск оттуда падает с невнятной ошибкой импорта.

# just на Windows по умолчанию ищет оболочку sh. Она в системе есть —
# C:\Program Files\Git\usr\bin\sh.exe, — но Git намеренно не добавляет этот
# каталог в PATH, чтобы юниксовые утилиты не перекрывали команды Windows.
# Поэтому из PowerShell just падал с «could not find the shell `sh`».
# PowerShell есть на любой Windows и не требует ничего доустанавливать.
set windows-shell := ["powershell.exe", "-NoLogo", "-Command"]

# Флаги для запуска чего-либо в готовом окружении.
#
# --frozen: не пересчитывать uv.lock. Без него uv может решить, что лок устарел,
#   пойти в сеть и пере-резолвить зависимости прямо посреди прогона тестов.
# --no-sync: не трогать .venv вообще. Установка — дело рецептов install-*,
#   а не побочный эффект `just test`.
run := "uv run --frozen --no-sync"

# Показать список команд
default:
    @just --list --unsorted

# --- установка ---
#
# uv sync по умолчанию ТОЧНЫЙ: приводит .venv ровно к тому, что объявлено
# выбранными экстрами и группами, и удаляет всё остальное. Поэтому здесь всюду
# --inexact: каждый рецепт про одну добавку, и `just install-gpu` не должен
# сносить torch, а `just install` — гигабайт библиотек CUDA.
# Привести окружение ровно к локу — отдельная команда reset-env.

# Поставить базовые зависимости (создаёт .venv, если его нет)
install:
    uv sync --inexact

# Доставить поддержку видеокарты NVIDIA (~1 ГБ)
install-gpu:
    uv sync --inexact --extra gpu

# Доставить движок синтеза Silero, ему нужен torch (~250 МБ)
install-silero:
    uv sync --inexact --extra silero

# Доставить инструменты разработки
#
# Хуки ставятся тем же рецептом, а не отдельным шагом: на свежем клоне
# `just install-dev` обязан сразу оставить и группу dev, и .git/hooks в
# согласованном состоянии — иначе `just all` следующим шагом падает на
# check-hooks, и первое впечатление от проекта — сломанная проверка.
# `just hooks` вызван из тела, а не через обычную зависимость just: зависимости
# исполняются ДО тела рецепта, а бинарник lefthook появляется в .venv только
# после uv sync. Проверено: без него `lefthook install` падает с «Failed to
# spawn: lefthook, program not found» — обратный порядок ломает именно то,
# что должен чинить.
install-dev:
    uv sync --inexact --group dev
    just hooks

# Привести окружение ровно к uv.lock: поставить всё и УДАЛИТЬ лишнее
#
# Единственный рецепт без --inexact. Нужен, когда окружение обросло
# экспериментами и хочется вернуться к проверенному состоянию.
reset-env:
    uv sync --all-extras --all-groups

# Полная установка: всё сразу
#
# То же самое действие: поставить все экстры и группы — значит привести
# окружение к локу целиком. Отдельное имя оставлено как привычный вход.
install-all: reset-env

# --- зависимости ---

# Пересчитать uv.lock после правки pyproject.toml
lock:
    uv lock

# Проверить, что uv.lock не разошёлся с pyproject.toml
locked:
    uv lock --check

# Выгрузить зависимости в формате requirements.txt — для отладки
#
# Файл в .gitignore: точка истины — uv.lock, а не выгрузка из него. Для
# pip-совместимости понадобились бы ещё --all-extras и --emit-index-url.
export:
    uv export --frozen --format requirements.txt --no-hashes --no-dev -o requirements-export.txt

# --- запуск ---

# Запустить приложение
run:
    {{ run }} python -m voxduo

# Запустить с подробными логами (в лог попадают и тексты)
debug:
    {{ run }} python -m voxduo --debug

# Показать сводку об окружении: версии, видеокарта, пути
check:
    {{ run }} python -m voxduo --check

# --- git-хуки ---
#
# lefthook.yml описывает pre-commit (ruff по застейдженным файлам) и pre-push
# (лок, типы, тесты). Хуки не гейт: --no-verify и LEFTHOOK=0 обходят их
# целиком, единственный настоящий гейт — обязательный джоб checks в защите
# main. Хуки только ускоряют обратную связь, до неё не подменяя.

# Поставить git-хуки из lefthook.yml
#
# validate второй строкой: опечатка в ключах конфига вскроется здесь, при
# установке, а не тихо на первом коммите.
hooks:
    {{ run }} lefthook install
    {{ run }} lefthook validate

# Проверить, что хуки стоят и не разошлись с lefthook.yml
#
# Часть just all: «зелёный just all» с этого момента означает и «хуки живы».
#
# Двух строк здесь ровно столько, сколько нужно: `check-install` вопреки своей
# же справке («1 – hooks are not installed or stale») сверяет только
# контрольную сумму конфига в .git/info/lefthook.checksum, а сами файлы хуков
# не смотрит. Проверено на lefthook 2.1.12: удаление обоих хуков при живом
# checksum даёт код 0, и только удаление самого checksum даёт 1. То есть
# свежий клон команда ловит (там нет ни хуков, ни checksum), а вот вручную
# удалённый или затёртый чужим `git init` хук — пропускает молча.
#
# Поэтому вторая строка проверяет то, ради чего рецепт и заведён: файлы хуков
# существуют. Обе проверки нужны — первая ловит расхождение с конфигом,
# вторая отсутствие самих хуков.
check-hooks:
    {{ run }} lefthook check-install
    @foreach ($h in 'pre-commit','pre-push') { if (-not (Test-Path ".git/hooks/$h")) { Write-Host "Хук $h не установлен. Поставить: just hooks"; exit 1 } }

# --- проверки ---

# Прогнать тесты
test:
    {{ run }} python -m pytest

# Тесты с отчётом о покрытии
cov:
    {{ run }} python -m pytest --cov=voxduo --cov-report=term-missing

# Проверить стиль и форматирование
#
# Обе команды отдельными строками: just обрывает рецепт на первой же
# неудаче, поэтому упавший линтер не спрячется за успешным форматтером.
# Форматирование проверяется и здесь, и в CI — иначе «у меня зелено»
# перестаёт означать «в CI зелено», а именно это расхождение мы и лечим.
lint:
    {{ run }} python -m ruff check .
    {{ run }} python -m ruff format --check .

# Проверить аннотации типов
#
# Платформа и версия Python зафиксированы в [tool.mypy], поэтому результат
# здесь и в CI одинаков. Проверено: с экстрой silero и без неё счёт совпадает.
types:
    {{ run }} python -m mypy

# Отформатировать и починить, что чинится автоматически
#
# check --fix сначала, format вторым: обратный порядок ломает то, что уже
# починил форматтер, — правки линтера уезжали бы неотформатированными, и
# коммит был бы зелёным при красном CI. Тот же порядок — в pre-commit хуке.
fmt:
    {{ run }} python -m ruff check --fix .
    {{ run }} python -m ruff format .

# Всё, что стоит прогнать перед коммитом
#
# check-hooks первым шагом: «зелёный just all» с этого момента означает и
# «хуки живы». Сам hooks сюда не входит — он пишет в .git, и это не должно
# быть побочным эффектом проверки.
all: check-hooks locked lint types test

# Прогон движков синтеза вживую: сеть, модели, звук
smoke:
    {{ run }} python scripts/smoke.py

# То же, но с воспроизведением результата
smoke-play:
    {{ run }} python scripts/smoke.py --play

# --- сборка и обслуживание ---

# Собрать voxduo.exe
build:
    {{ run }} python -m PyInstaller voxduo.spec --noconfirm

# Открыть папку с логами
logs:
    explorer.exe "$env:LOCALAPPDATA\VoxDuo\logs"

# --- защита ветки main ---
#
# Ruleset «main protection» требует зелёный джоб checks перед мержем и
# запрещает force-push и удаление ветки. Список обхода пуст намеренно: внести
# туда владельца — значит выключить защиту, потому что мержит как раз он.
#
# Аварийный выход существует ровно для одного случая: Actions недоступны, а
# влить нужно сейчас. Тогда `just unprotect`, мерж, `just protect` обратно.
# Не для случая «проверка красная, но мне кажется, что всё нормально».
#
# Два ограничения, найденные на практике:
#  * enforcement=evaluate требует Enterprise, поэтому снятие — только disabled;
#  * PowerShell 5.1 ломает аргумент gh, если внутри выражения --jq есть
#    двойные кавычки: строка разбивается, и gh получает два аргумента вместо
#    одного. Поэтому фильтр по имени заменён на id, а вывод — на @tsv.

# id ruleset. Если правило пересоздадут, новый покажет `just protection`
ruleset := "22542245"

# Показать состояние защиты main
protection:
    gh api repos/TheDragonBald/voxduo/rulesets --jq '.[]|[.id,.name,.enforcement]|@tsv'

# Снять защиту main (аварийно; вернуть сразу же через just protect)
unprotect:
    gh api -X PUT repos/TheDragonBald/voxduo/rulesets/{{ ruleset }} -f enforcement=disabled --jq '.enforcement'

# Вернуть защиту main
protect:
    gh api -X PUT repos/TheDragonBald/voxduo/rulesets/{{ ruleset }} -f enforcement=active --jq '.enforcement'

# Убрать временные файлы сборки и кэши
#
# Проверяем существование перед удалением, а не глушим ошибки через
# -ErrorAction SilentlyContinue: тот прячет сообщение, но рецепт всё равно
# завершается с кодом 1, и следующая строка не выполняется.
# Кэши ищем только в своих папках — внутри .venv их под тысячу.
clean:
    foreach ($p in 'build','dist','.pytest_cache','.ruff_cache','.mypy_cache','htmlcov','.coverage') { if (Test-Path $p) { Remove-Item -Recurse -Force $p } }
    foreach ($d in 'voxduo','tests','scripts') { if (Test-Path $d) { Get-ChildItem $d -Recurse -Directory -Filter __pycache__ | ForEach-Object { Remove-Item -Recurse -Force $_.FullName } } }
