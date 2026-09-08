# Идеи вне скоупа

Всё, что показалось полезным по ходу работы, но не входило в текущую задачу.
**Ничего отсюда не реализуется без явного решения** — список существует, чтобы
идеи не терялись.

Каждая идея продублирована в GitHub issue: там обсуждение, метки и связь с PR.
Перед тем как завести новый, ищем похожие по метке `idea` — близкое
дополняем комментарием, а не плодим соседний issue с разницей в одно слово.

Метки: `area:*` — область, `cost:S` — часы, `cost:M` — день-два,
`cost:L` — неделя и больше.

---

## Дёшево и бьёт в ежедневный сценарий

| Идея | Метки | Issue |
|---|---|---|
| Распознавание готового аудиофайла перетаскиванием: голосовое из мессенджера сразу в текст | `area:stt` `cost:S` |  [#9](https://github.com/TheDragonBald/voxduo/issues/9) |
| Автостоп по тишине: замолчал на две секунды — запись остановилась сама | `area:stt` `cost:S` |  [#10](https://github.com/TheDragonBald/voxduo/issues/10) |
| Профили промптов: «программирование» / «общение» / «диктовка» в один клик | `area:stt` `cost:S` |  [#11](https://github.com/TheDragonBald/voxduo/issues/11) |
| Пробел = запись, локальный хоткей внутри окна | `area:ui` `cost:S` |  [#12](https://github.com/TheDragonBald/voxduo/issues/12) |
| Перевод на английский: Whisper умеет `task="translate"`, нужна одна галочка | `area:stt` `cost:S` |  [#13](https://github.com/TheDragonBald/voxduo/issues/13) |
| Осциллограмма вместо полоски уровня — на canvas это двадцать строк | `area:ui` `cost:S` |  [#14](https://github.com/TheDragonBald/voxduo/issues/14) |
| Экспорт истории в Markdown | `area:ui` `cost:S` |  [#15](https://github.com/TheDragonBald/voxduo/issues/15) |

## Средняя стоимость

| Идея | Метки | Issue |
|---|---|---|
| Обучаемый словарь: правишь распознанный текст — приложение предлагает запомнить замену | `area:stt` `cost:M` |  [#16](https://github.com/TheDragonBald/voxduo/issues/16) |
| Экспорт субтитров SRT/VTT — тайм-коды уже есть при `word_timestamps` | `area:stt` `cost:M` |  [#17](https://github.com/TheDragonBald/voxduo/issues/17) |
| Иконка в трее и сворачивание туда | `area:ui` `cost:M` |  [#18](https://github.com/TheDragonBald/voxduo/issues/18) |
| Статистика: сколько надиктовано минут и слов | `area:ui` `cost:M` |  [#19](https://github.com/TheDragonBald/voxduo/issues/19) |
| Веб-режим: бэкенд станет HTTP-сервисом, можно открыть с телефона в той же сети и диктовать на компьютер | `area:infra` `cost:M` |  [#20](https://github.com/TheDragonBald/voxduo/issues/20) |
| Мультиязычный интерфейс | `area:ui` `cost:M` |  [#21](https://github.com/TheDragonBald/voxduo/issues/21) |
| Настраиваемые горячие клавиши внутри окна | `area:ui` `cost:M` |  [#22](https://github.com/TheDragonBald/voxduo/issues/22) |

## Дорого или спорно

| Идея | Метки | Issue |
|---|---|---|
| Стриминговое распознавание: после переезда на WebSocket становится реальным, останется резать аудио на куски | `area:stt` `cost:L` |  [#23](https://github.com/TheDragonBald/voxduo/issues/23) |
| Диаризация — кто говорит. `pyannote` требует токен и много ресурсов | `area:stt` `cost:L` |  [#24](https://github.com/TheDragonBald/voxduo/issues/24) |
| LLM-полировка текста: либо API-ключ, либо ещё 4 ГБ локальной модели в конкуренции с Whisper за видеопамять | `area:stt` `cost:L` |  [#25](https://github.com/TheDragonBald/voxduo/issues/25) |

## Отклонено в опросе 7 сентября 2026

Записано на случай, если решение изменится.

| Идея | Метки | Issue |
|---|---|---|
| Глобальный хоткей push-to-talk поверх всех окон | `area:ui` `cost:M` |  [#26](https://github.com/TheDragonBald/voxduo/issues/26) |
| Автокопирование в буфер сразу после распознавания | `area:ui` `cost:S` |  [#27](https://github.com/TheDragonBald/voxduo/issues/27) |
| Автовставка в активное окно эмуляцией Ctrl+V | `area:ui` `cost:M` |  [#28](https://github.com/TheDragonBald/voxduo/issues/28) |

## Найдено при проверке связки (фаза Ф0)

| Идея | Метки | Issue |
|---|---|---|
| Не запускать второй экземпляр, а фокусировать существующее окно | `area:infra` `cost:S` | [#6](https://github.com/TheDragonBald/voxduo/issues/6) |
| Автопереподключение WebSocket и видимое состояние связи | `area:ui` `cost:S` | [#7](https://github.com/TheDragonBald/voxduo/issues/7) |
| Проверять собранный `.exe` в CI: HTTP, статика, WebSocket | `area:infra` `cost:S` | [#8](https://github.com/TheDragonBald/voxduo/issues/8) |

## Найдено при настройке процесса (фаза Ф1)

| Идея | Метки | Issue |
|---|---|---|
| Хук проверяет факт прогона тестов, а не только напоминает о нём | `area:infra` `cost:M` | [#32](https://github.com/TheDragonBald/voxduo/issues/32) |
| Оформить ритуалы проекта отдельным скиллом, чтобы срабатывали по триггеру | `area:docs` `cost:M` | [#33](https://github.com/TheDragonBald/voxduo/issues/33) |
| Тесты для `scripts/session_snapshot.py` — разбор плана сейчас не покрыт | `area:infra` `cost:S` | [#34](https://github.com/TheDragonBald/voxduo/issues/34) |
| Резервная копия локальных документов вне репозитория | `area:infra` `cost:S` | [#35](https://github.com/TheDragonBald/voxduo/issues/35) |

---

## Уже реализовано

Убрано из списка, чтобы не всплывало снова.

- **Озвучить буфер обмена** — кнопка «Из буфера» в режиме синтеза
