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
- Python 3.13
- Около 8 ГБ на диске: модели, библиотеки, окружение
- Видеокарта NVIDIA — **необязательно**, но с ней распознавание идёт в
  разы быстрее. На RTX 2060 SUPER `large-v3-turbo` обрабатывает запись
  в 12 раз быстрее реального времени

## Установка

```powershell
git clone https://github.com/TheDragonBald/voxduo.git
cd voxduo
powershell -ExecutionPolicy Bypass -File install.ps1 -Shortcut
```

Скрипт создаст изолированное окружение, поставит зависимости, сам определит
видеокарту и подтянет для неё библиотеки CUDA. Устанавливать CUDA Toolkit
отдельно не нужно.

Дополнительно:

```powershell
.\install.ps1 -Silero   # добавить движок Silero (нужен torch, ~250 МБ)
.\install.ps1 -NoGpu    # не ставить поддержку видеокарты
.\install.ps1 -Dev      # инструменты разработки
```

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
.venv\Scripts\python.exe -m voxduo --check
```

| Симптом | Что делать |
|---|---|
| Устройств CUDA: 0, хотя карта есть | Поставьте `requirements-gpu.txt`, обновите драйвер NVIDIA |
| Синтез через edge-tts падает с 403 | Укажите текущую версию браузера в настройках (видно на `edge://settings/help`) или обновите пакет: `pip install -U edge-tts` |
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
just --list      # все команды
just all         # линтер и тесты перед коммитом
just smoke       # живой прогон движков синтеза
just check       # сводка окружения
```

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

Requires Windows 10/11 x64 and Python 3.13. An NVIDIA GPU is optional but
makes recognition several times faster; CUDA libraries are installed through
pip, no CUDA Toolkit needed.

Code is GPL-3.0. Models are downloaded at runtime and keep their own
licences — the defaults are MIT and CC0, non-commercial voices are available
but clearly marked. See the licence table above.
