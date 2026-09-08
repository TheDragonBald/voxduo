# Установка VoxDuo.
#
# Ставит uv, а он уже создаёт окружение строго по uv.lock — тем же самым, что
# проверяется в CI и на котором собирается .exe. Отдельно решается частая
# путаница: python из PATH может оказаться не тем, где стоят пакеты, поэтому
# интерпретатором заведует uv, а ярлык запускает pythonw именно из .venv.
#
# Запуск:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Параметры:
#   -Silero    доставить движок синтеза Silero (нужен torch, ~250 МБ)
#   -Dev       доставить инструменты разработки
#   -NoGpu     не ставить поддержку видеокарты, даже если она есть
#   -Shortcut  создать ярлык на рабочем столе
#   -Yes       не спрашивать подтверждения (для автоматизации)
#
# ВАЖНО про повторные запуски: набор ключей задаёт окружение ЦЕЛИКОМ. Запуск
# без -Silero удалит Silero, поставленный прошлый раз. Так сделано намеренно —
# окружение должно определяться командой, а не историей запусков, — но молча
# этого не происходит: скрипт сначала покажет, что исчезнет, и спросит.

[CmdletBinding()]
param(
    [switch]$Silero,
    [switch]$Dev,
    [switch]$NoGpu,
    [switch]$Shortcut,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'

# Консоль Windows по умолчанию не в UTF-8, и русский текст выводится
# кракозябрами. Файл сохранён с BOM по той же причине: без него
# PowerShell 5.1 читает его в ANSI и спотыкается на кириллице.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

function Write-Step($text) { Write-Host "`n==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "    $text" -ForegroundColor Yellow }

# Версию читаем разбором `uv --version`: этот вывод есть у всех версий, в
# отличие от подкоманды self version, появившейся позже.
function Get-UvVersion {
    $raw = & uv --version 2>$null
    if ($LASTEXITCODE -ne 0 -or -not $raw) { return $null }
    if ($raw -match '(\d+\.\d+\.\d+)') { return [version]$Matches[1] }
    return $null
}

Write-Host "VoxDuo — установка" -ForegroundColor White
Write-Host "Папка: $root"

# --- uv ---
# Нижняя граница та же, что в required-version у pyproject.toml. Ниже неё uv
# честно откажется работать, поэтому проверяем ДО того, как звать его всерьёз.
$minUv = [version]'0.12.10'

Write-Step "Проверяем uv"
$uvVersion = Get-UvVersion

if ($null -eq $uvVersion) {
    Write-Ok "не найден, устанавливаем"
    $env:UV_INSTALL_DIR = if ($env:UV_INSTALL_DIR) { $env:UV_INSTALL_DIR } else { Join-Path $env:USERPROFILE '.local\bin' }
    Invoke-RestMethod https://astral.sh/uv/install.ps1 | Invoke-Expression

    # Инсталлятор правит Environment.Path в реестре — в ТЕКУЩЕЙ сессии этого
    # не видно, и следующая же строка упала бы с «uv не найден». Prepend, а не
    # append: иначе более старый uv из другого источника продолжит выигрывать.
    $env:Path = "$($env:UV_INSTALL_DIR);$env:Path"

    $uvVersion = Get-UvVersion
    if ($null -eq $uvVersion) {
        Write-Warn "uv установлен, но не запускается. Откройте новое окно PowerShell и повторите."
        exit 1
    }
    Write-Ok "установлен uv $uvVersion"
} elseif ($uvVersion -lt $minUv) {
    Write-Ok "найден uv $uvVersion, нужен $minUv и новее — обновляем"

    # У сборок из winget самообновление отключено: `uv self update` завершается
    # с ошибкой и советует ровно то, что не сработает. Поэтому сначала
    # выясняем, откуда uv взялся.
    $fromWinget = $false
    try {
        winget list --exact --id astral-sh.uv --accept-source-agreements | Out-Null
        $fromWinget = ($LASTEXITCODE -eq 0)
    } catch { }

    if ($fromWinget) {
        winget upgrade --exact --id astral-sh.uv --accept-source-agreements --accept-package-agreements
    } else {
        & uv self update
        if ($LASTEXITCODE -ne 0) {
            Write-Warn "не удалось обновить uv автоматически"
            Write-Warn "обновите вручную: https://docs.astral.sh/uv/getting-started/installation/"
            exit 1
        }
    }

    $uvVersion = Get-UvVersion
    if ($null -eq $uvVersion -or $uvVersion -lt $minUv) {
        Write-Warn "после обновления всё ещё $uvVersion, а нужен $minUv и новее"
        exit 1
    }
    Write-Ok "обновлён до $uvVersion"
} else {
    Write-Ok "uv $uvVersion"
}

# --- интерпретатор ---
# Версия берётся из .python-version, отдельной настройки не требуется.
#
# `uv python install` вызывается ТОЛЬКО если подходящего интерпретатора нет:
# эта команда ставит собственную сборку безусловно и не смотрит на
# python-preference = "system". На машине с уже установленным 3.13 она молча
# качала бы лишние двадцать мегабайт.
Write-Step "Проверяем Python"
$found = & uv python find 2>$null
if ($LASTEXITCODE -eq 0 -and $found) {
    Write-Ok "найден: $found"
} else {
    Write-Ok "подходящего нет, ставим"
    & uv python install
    if ($LASTEXITCODE -ne 0) {
        Write-Warn "не удалось подготовить Python — см. сообщение выше"
        exit 1
    }
    Write-Ok "готово"
}

# --- видеокарта ---
Write-Step "Проверяем видеокарту"
$hasGpu = $false
try {
    $gpu = & nvidia-smi --query-gpu=name,memory.total --format=csv,noheader 2>$null
    if ($LASTEXITCODE -eq 0 -and $gpu) {
        $hasGpu = $true
        Write-Ok "найдена: $gpu"
    }
} catch { }

if (-not $hasGpu) {
    Write-Ok "видеокарта NVIDIA не найдена — распознавание пойдёт на процессоре"
} elseif ($NoGpu) {
    Write-Ok "пропускаем поддержку GPU по вашему указанию (-NoGpu)"
}

# --- состав окружения ---
# Один вызов uv sync вместо четырёх pip install: набор экстра собирается
# заранее и применяется разом, поэтому промежуточных несогласованных
# состояний окружения не возникает.
$syncArgs = @('sync', '--locked')
if ($hasGpu -and -not $NoGpu) { $syncArgs += @('--extra', 'gpu') }
if ($Silero)                  { $syncArgs += @('--extra', 'silero') }
if ($Dev)                     { $syncArgs += @('--group', 'dev') }

# --- предохранитель ---
# uv sync точный: он приводит .venv ровно к запрошенному составу и удаляет
# остальное. Это правильно — окружение должно определяться командой, — но
# забытый ключ стоил бы гигабайта скачанного молча. Поэтому сначала dry-run.
Write-Step "Смотрим, что изменится"
# uv печатает план в stderr, поэтому 2>&1 обязателен. Но Windows PowerShell 5.1
# заворачивает каждую строку stderr нативной программы в ErrorRecord, и при
# $ErrorActionPreference = 'Stop' первая же строка обрывает скрипт — до того,
# как пользователь увидит предупреждение. Поэтому на время вызова возвращаем
# 'Continue', а результат проверяем сами по $LASTEXITCODE.
$prevEap = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
$plan = & uv @syncArgs --dry-run 2>&1 | ForEach-Object { $_.ToString() }
$planExit = $LASTEXITCODE
$ErrorActionPreference = $prevEap

if ($planExit -ne 0) {
    $plan | ForEach-Object { Write-Host $_ }
    Write-Warn "не удалось построить план установки"
    exit 1
}

$removals = $plan | Where-Object { $_ -match '^\s*-\s' }
if ($removals -and -not $Yes) {
    Write-Warn "Из окружения будет УДАЛЕНО:"
    $removals | ForEach-Object { Write-Host "    $_" -ForegroundColor Yellow }
    Write-Warn "Набор ключей задаёт окружение целиком. Чтобы сохранить эти пакеты,"
    Write-Warn "перезапустите с нужными ключами: -Silero (Silero), -Dev (разработка)."
    # В неинтерактивной сессии (CI, запуск из другого скрипта) Read-Host читает
    # EOF и падает. Отказ там честнее вопроса, на который некому ответить.
    if ([Environment]::UserInteractive -and -not [Console]::IsInputRedirected) {
        $answer = Read-Host "Продолжить? (y/N)"
        if ($answer -ne 'y' -and $answer -ne 'Y') {
            Write-Host "Отменено." -ForegroundColor White
            exit 1
        }
    } else {
        Write-Warn "Консоль неинтерактивна, спросить некого. Повторите с -Yes,"
        Write-Warn "если удаление действительно нужно."
        exit 1
    }
} elseif (-not $removals) {
    Write-Ok "ничего не удаляется"
}

Write-Step "Ставим зависимости"
& uv @syncArgs
if ($LASTEXITCODE -ne 0) {
    Write-Warn "установка не удалась — см. сообщение выше"
    exit 1
}
Write-Ok "готово"

# --- проверка ---
Write-Step "Проверяем окружение"
& uv run --frozen --no-sync python -m voxduo --check
if ($LASTEXITCODE -ne 0) {
    Write-Warn "приложение не запустилось — см. сообщение выше"
    exit 1
}

# --- ярлык ---
if ($Shortcut) {
    Write-Step "Создаём ярлык на рабочем столе"
    # pythonw, а не python: иначе рядом с окном висит чёрная консоль
    $venvPythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
    if (-not (Test-Path $venvPythonw)) {
        Write-Warn "не найден $venvPythonw — ярлык не создан"
    } else {
        $desktop = [Environment]::GetFolderPath('Desktop')
        $linkPath = Join-Path $desktop 'VoxDuo.lnk'

        $shell = New-Object -ComObject WScript.Shell
        $link = $shell.CreateShortcut($linkPath)
        $link.TargetPath = $venvPythonw
        $link.Arguments = '-m voxduo'
        $link.WorkingDirectory = $root
        $link.Description = 'VoxDuo — голос в текст и текст в голос'
        $link.Save()
        Write-Ok $linkPath
    }
}

Write-Host "`nГотово." -ForegroundColor Green
Write-Host "Запуск:  .venv\Scripts\pythonw.exe -m voxduo"
Write-Host "Или:     just run"
Write-Host ""
Write-Host "При первом распознавании скачается модель Whisper — около 3 ГБ." -ForegroundColor Yellow
