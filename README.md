# VoxDuo

Распознавание и синтез речи на русском языке. Работает локально на вашей
машине: надиктовали — получили текст с расставленной пунктуацией, вставили
текст — услышали живой голос.

Написано для себя и ежедневного использования, выложено в открытый доступ.

## Что умеет

**Голос → текст.** Whisper `large-v3` или `large-v3-turbo` на выбор. Знаки
препинания расставляются сами, английские термины в русской речи остаются
латиницей: «закоммитил фикс, но CI упал на линтере — надо пересобрать
Docker-образ». Тишина и паузы не превращаются в выдуманные фразы.

**Текст → голос.** Три движка: нейроголоса Microsoft Edge (звучат живее
всего, нужен интернет), Silero и Piper (работают офлайн). Если основной
движок недоступен, озвучит следующий — и скажет об этом.

**Ещё.** История последних пяти записей в каждом режиме, переживает
перезапуск. Озвучки можно переслушать без повторного синтеза и сохранить
файлом. Светлая и тёмная темы. Копирование в буфер подтверждается сразу
тремя способами, чтобы точно не пропустить.

## Требования

- Windows 10 или 11, 64 бита
- Python 3.13 — если его нет, установщик подтянет сам
- Около 8 ГБ на диске: модели, библиотеки, окружение
- Видеокарта NVIDIA — **необязательно**, но с ней распознавание идёт в
  разы быстрее. На RTX 2060 SUPER `large-v3-turbo` обрабатывает запись
  в 12 раз быстрее реального времени

## Установка

### Готовая сборка — если Python не нужен

Скачайте `voxduo-windows-x64.zip` со страницы
[релизов](https://github.com/TheDragonBald/voxduo/releases), распакуйте,
запустите `voxduo.exe`. Устанавливать ничего не требуется.

Чем сборка отличается от установки из исходников:

- **распознавание идёт на процессоре**, даже если видеокарта есть. Библиотеки
  CUDA проприетарные и весят около гигабайта, поэтому в бинарник не входят;
- **движок Silero недоступен** — ему нужен torch, ещё четверть гигабайта.
  Синтез работает через edge-tts и Piper.

Если у вас есть видеокарта NVIDIA, ставьте из исходников: разница в скорости
распознавания измеряется разами, а не процентами.

### Из исходников — полная версия

```powershell
git clone https://github.com/TheDragonBald/voxduo.git
cd voxduo
powershell -ExecutionPolicy Bypass -File install.ps1 -Shortcut
```

Скрипт поставит [uv](https://docs.astral.sh/uv/), если его нет, создаст
окружение строго по `uv.lock`, сам определит видеокарту и подтянет для неё
библиотеки CUDA. Устанавливать ни Python, ни CUDA Toolkit отдельно не нужно.

Дополнительно:

```powershell
.\install.ps1 -Silero   # добавить движок Silero (нужен torch, ~250 МБ)
.\install.ps1 -NoGpu    # не ставить поддержку видеокарты
.\install.ps1 -Dev      # инструменты разработки
```

**Ключи задают окружение целиком, а не добавляют к нему.** Запуск без
`-Silero` уберёт Silero, поставленный в прошлый раз: окружение определяется
командой, а не историей запусков — так у всех оно одинаковое и совпадает с
тем, на котором собирается готовая сборка. Молча ничего не пропадёт — скрипт
сначала покажет, что именно удалит, и спросит подтверждения.

## Запуск

```powershell
.venv\Scripts\pythonw.exe -m voxduo
```

Или ярлыком с рабочего стола, если ставили с `-Shortcut`.

При первом распознавании скачается модель — около 3 ГБ для `large-v3` или
1.6 ГБ для `large-v3-turbo`. Дальше всё работает без сети (кроме edge-tts).

## Качество распознавания

Главный рычаг — **подсказка** в настройках. Whisper подстраивает стиль
расшифровки под неё, поэтому перечислите там термины ровно так, как хотите
их видеть в тексте:

> Обсуждаем разработку: Python, JavaScript, React, Docker, API, commit,
> merge request, CI/CD. Речь на русском с английскими терминами.

Второй рычаг — **словарь замен** там же. Если модель упорно пишет
«джаваскрипт», добавьте строку `джаваскрипт = JavaScript`. Замены
применяются целыми словами, так что «питончик» не превратится в «Pythonчик».

Честная оговорка: Whisper рассчитан на один язык в записи. Связка модели,
подсказки и словаря хорошо закрывает типичный случай — русская речь с
латинскими терминами, — но двуязычной модель от этого не становится.

## Если что-то не работает

Начните с диагностики — она показывает версии, видеокарту и пути:

```powershell
just check
```

Без `just` — напрямую: `.venv\Scripts\python.exe -m voxduo --check`

| Симптом | Что делать |
|---|---|
| Устройств CUDA: 0, хотя карта есть | Выполните `just install-gpu`, обновите драйвер NVIDIA |
| Синтез через edge-tts падает с 403 | Укажите текущую версию браузера в настройках (видно на `edge://settings/help`) или обновите пакет: поднимите версию `edge-tts` в `pyproject.toml`, затем `uv lock --upgrade-package edge-tts` и `just install` |
| Распознаётся пустота | Проверьте выбранный микрофон в настройках: индикатор рядом с кнопкой должен реагировать на голос |
| Окно зависает при запуске | Модель качается в фоне, первый раз это несколько минут; смотрите журнал |

Журнал — в `%LOCALAPPDATA%\VoxDuo\logs\voxduo.log`, кнопка «Открыть папку с
логами» есть в настройках. Тексты расшифровок в журнал **не пишутся**, только
длительность, модель и время обработки.

## Лицензии

Код — **GPL-3.0**. Выбор продиктован зависимостями: Piper распространяется
под GPL-3.0, и импорт делает производной работой всё, что его использует.

Модели и голоса скачиваются на вашу машину и живут по своим правилам.
По умолчанию используется только то, что не ограничено:

| Что | Лицензия |
|---|---|
| Whisper `large-v3`, `large-v3-turbo` | MIT |
| Silero `v5_cis_base` | MIT |
| Piper `denis`, `dmitri` | CC0 |
| Silero `v5_ru`, `v5_5_ru` | CC BY-NC — **некоммерческое** |
| Piper `ruslan` | CC BY-NC-SA — **некоммерческое** |
| Piper `irina` | лицензия датасета не указана |

Голоса с ограничениями доступны в списке, но помечены явно.

**Про edge-tts.** Сама библиотека под LGPL-3.0, но обращается она к API
Microsoft Edge неофициально: условий использования этого интерфейса
сторонними приложениями Microsoft не публиковала. Движок отключается, и
без него всё работает офлайн на Silero и Piper.

## Разработка

```powershell
just install-dev # инструменты разработки: ruff, pytest, PyInstaller
just --list      # все команды
just all         # проверка лока, линтер и тесты перед коммитом
just smoke       # живой прогон движков синтеза
just check       # сводка окружения
```

Зависимости живут в `pyproject.toml`, точные версии — в `uv.lock`; он
коммитится и руками не правится. После правки `pyproject.toml` — `just lock`.
Вернуть окружение ровно к локу, выбросив всё лишнее, — `just reset-env`.

---

## English

**VoxDuo** — speech to text and text to speech for Russian, running locally
on Windows.

Speech recognition uses Whisper `large-v3` or `large-v3-turbo` through
faster-whisper, with punctuation and Latin-script technical terms preserved
inside Russian speech. Speech synthesis offers three engines: Microsoft Edge
neural voices (online, most natural), Silero and Piper (both offline), with
automatic fallback between them.

Also: five-entry history per mode surviving restarts, replayable synthesised
audio, light and dark themes, and clear copy confirmation.

Requires Windows 10/11 x64. Dependencies — Python 3.13 included — are managed
by [uv](https://docs.astral.sh/uv/) and pinned in `uv.lock`; `install.ps1`
sets everything up. An NVIDIA GPU is optional but makes recognition several
times faster, and its CUDA libraries come as regular wheels, so no CUDA
Toolkit is needed.

Code is GPL-3.0. Models are downloaded at runtime and keep their own
licences — the defaults are MIT and CC0, non-commercial voices are available
but clearly marked. See the licence table above.
