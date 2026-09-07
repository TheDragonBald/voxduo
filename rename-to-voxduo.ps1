# Переименование папки проекта в VoxDuo.
#
# Зачем отдельный скрипт. Пока папка является рабочей директорией открытой
# сессии или редактора, Windows держит её занятой и переименование падает с
# «The process cannot access the file because it is being used by another
# process». Проверено: переименование соседних папок при этом проходит, то
# есть дело именно в удержании.
#
# Поэтому: закройте редактор и терминалы, открытые в папке проекта, затем
# запустите скрипт из ЛЮБОГО другого места, например из корня диска:
#
#   powershell -ExecutionPolicy Bypass -File "D:\...\rumor_n_gossip\rename-to-voxduo.ps1"
#
# Скрипт сам уходит из папки перед переименованием.

[CmdletBinding()]
param(
    [string]$NewName = 'VoxDuo'
)

$ErrorActionPreference = 'Stop'

# Консоль Windows по умолчанию не в UTF-8, и русский текст выводится
# кракозябрами. Файл сохранён с BOM по той же причине: без него
# PowerShell 5.1 читает его в ANSI и спотыкается на кириллице.
try { [Console]::OutputEncoding = [System.Text.Encoding]::UTF8 } catch { }

$source = Split-Path -Parent $MyInvocation.MyCommand.Path
$parent = Split-Path -Parent $source
$current = Split-Path -Leaf $source
$target = Join-Path $parent $NewName

Write-Host "Папка сейчас : $source"
Write-Host "Станет       : $target"

if ($current -eq $NewName) {
    Write-Host "`nПапка уже называется $NewName — делать нечего." -ForegroundColor Green
    exit 0
}

if (Test-Path $target) {
    Write-Host "`n$target уже существует. Переименование отменено." -ForegroundColor Red
    exit 1
}

# Уходим из папки, иначе сам скрипт будет её держать
Set-Location $parent

try {
    Rename-Item -LiteralPath $source -NewName $NewName -ErrorAction Stop
} catch {
    Write-Host "`nНе удалось переименовать: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host ""
    Write-Host "Папку кто-то держит. Обычно это:" -ForegroundColor Yellow
    Write-Host "  - открытый в ней VS Code или другой редактор"
    Write-Host "  - терминал, у которого она текущая"
    Write-Host "  - запущенное приложение из .venv"
    Write-Host ""
    Write-Host "Закройте их и запустите скрипт снова." -ForegroundColor Yellow
    exit 1
}

Write-Host "`nГотово: $target" -ForegroundColor Green
Write-Host ""
Write-Host "Что дальше:" -ForegroundColor Cyan
Write-Host "  1. Откройте проект по новому пути."
Write-Host "  2. Старый ярлык 'voice_to_text.py — ярлык' больше не работает —"
Write-Host "     создайте новый: install.ps1 -Shortcut"
Write-Host "  3. Виртуальное окружение переезд переживает, переустановка не нужна."
