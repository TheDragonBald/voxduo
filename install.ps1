# Установка VoxDuo.
#
# Создаёт изолированное окружение, ставит зависимости и определяет, есть ли
# видеокарта NVIDIA. Отдельно решает частую путаницу: python из PATH может
# оказаться не тем, где стоят пакеты, поэтому интерпретатор выбирается явно,
# а ярлык запускает pythonw именно из .venv.
#
# Запуск:
#   powershell -ExecutionPolicy Bypass -File install.ps1
#
# Параметры:
#   -Silero    доставить движок синтеза Silero (нужен torch, ~250 МБ)
#   -Dev       доставить инструменты разработки
#   -NoGpu     не ставить поддержку видеокарты, даже если она есть
#   -Shortcut  создать ярлык на рабочем столе

[CmdletBinding()]
param(
    [switch]$Silero,
    [switch]$Dev,
    [switch]$NoGpu,
    [switch]$Shortcut
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

Write-Host "VoxDuo — установка" -ForegroundColor White
Write-Host "Папка: $root"

# --- интерпретатор ---
# Берём 3.13 явно: под 3.14 колёса есть не у всех зависимостей,
# а python из PATH вообще может оказаться без пакетов.
Write-Step "Ищем Python 3.13"
$python = $null
foreach ($candidate in @('py -3.13', 'C:\Python313\python.exe')) {
    try {
        $parts = $candidate -split ' ', 2
        $exe = $parts[0]
        $args = if ($parts.Count -gt 1) { $parts[1] } else { $null }
        $version = if ($args) { & $exe $args --version 2>$null } else { & $exe --version 2>$null }
        if ($LASTEXITCODE -eq 0 -and $version -match '3\.13') {
            $python = $candidate
            Write-Ok "$candidate -> $version"
            break
        }
    } catch { }
}

if (-not $python) {
    Write-Warn "Python 3.13 не найден."
    Write-Warn "Скачать: https://www.python.org/downloads/release/python-3132/"
    Write-Warn "При установке отметьте 'Add python.exe to PATH'."
    exit 1
}

# --- окружение ---
Write-Step "Создаём окружение .venv"
if (Test-Path '.venv') {
    Write-Ok ".venv уже есть, используем его"
} else {
    $parts = $python -split ' ', 2
    if ($parts.Count -gt 1) { & $parts[0] $parts[1] -m venv .venv } else { & $parts[0] -m venv .venv }
    Write-Ok "создано"
}

$venvPython = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $venvPython)) {
    Write-Warn "Не удалось создать .venv — проверьте права на папку"
    exit 1
}

Write-Step "Обновляем pip"
& $venvPython -m pip install -q --upgrade pip
Write-Ok "готово"

Write-Step "Ставим основные зависимости (~350 МБ)"
& $venvPython -m pip install -r requirements.txt
Write-Ok "готово"

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
} else {
    Write-Step "Ставим библиотеки CUDA (~1 ГБ, это займёт время)"
    & $venvPython -m pip install -r requirements-gpu.txt
    Write-Ok "готово"
}

if ($Silero) {
    Write-Step "Ставим torch для движка Silero (~250 МБ)"
    & $venvPython -m pip install -r requirements-silero.txt
    Write-Ok "готово"
}

if ($Dev) {
    Write-Step "Ставим инструменты разработки"
    & $venvPython -m pip install -r requirements-dev.txt
    Write-Ok "готово"
}

# --- проверка ---
Write-Step "Проверяем окружение"
& $venvPython -m voxduo --check

# --- ярлык ---
if ($Shortcut) {
    Write-Step "Создаём ярлык на рабочем столе"
    # pythonw, а не python: иначе рядом с окном висит чёрная консоль
    $venvPythonw = Join-Path $root '.venv\Scripts\pythonw.exe'
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

Write-Host "`nГотово." -ForegroundColor Green
Write-Host "Запуск:  .venv\Scripts\pythonw.exe -m voxduo"
Write-Host "Или:     just run"
Write-Host ""
Write-Host "При первом распознавании скачается модель Whisper — около 3 ГБ." -ForegroundColor Yellow
