"""Приведение расшифровки в читаемый вид.

Три независимых шага, каждый решает свою задачу:

* Словарь замен — лечит то, чего не исправить настройками Whisper: модель
  устойчиво пишет «джаваскрипт» вместо «JavaScript». Словарь пополняется
  пользователем под личный лексикон.
* Чистка галлюцинаций — на паузах и в тишине Whisper дописывает фразы из
  обучающих данных: «Продолжение следует…», «Субтитры сделал…». Фильтр VAD
  убирает большую часть, но не всё.
* Нормализация пробелов — косметика: лишний пробел перед запятой, двойные
  пробелы, забытая заглавная в начале.
"""

from __future__ import annotations

import re

# Фразы, которых в реальной диктовке не бывает: это следы субтитров из
# обучающей выборки Whisper. Удаляем только когда они занимают строку
# целиком — иначе можно отрезать кусок настоящей речи.
HALLUCINATION_PATTERNS: tuple[str, ...] = (
    r"продолжение следует\.*",
    r"субтитры (?:сделал|создавал|подготовил).*",
    r"субтитр[ыи]{1,2}\s+и\s+редактура[^.!?]*",
    r"редактор субтитров.*",
    r"корректор.*",
    r"спасибо за просмотр!*",
    r"подписывайтесь на канал!*",
    r"добро пожаловать на наш канал!*",
    r"поставьте лайк.*",
    r"дословный перевод.*",
)

_HALLUCINATION_RE = re.compile(
    r"^\s*(?:" + "|".join(HALLUCINATION_PATTERNS) + r")\s*$",
    re.IGNORECASE,
)

# Знаки, перед которыми пробел не ставится
_SPACE_BEFORE_PUNCT = re.compile(r"\s+([,.!?;:%)\]])")
_SPACE_AFTER_OPEN = re.compile(r"([(\[])\s+")
_MULTISPACE = re.compile(r"[ \t]{2,}")

# Кириллические строчные, включая ё
_CYRILLIC_LOWER = re.compile(r"[а-яё]")


def _is_word_char(char: str) -> bool:
    """Считается ли символ частью слова с точки зрения регулярных выражений."""
    return char.isalnum() or char == "_"


def apply_replacements(text: str, replacements: dict[str, str]) -> str:
    """Заменяет слова по словарю, не задевая части других слов.

    Поиск регистронезависимый, длинные ключи применяются первыми — иначе
    «джава скрипт» никогда не сработал бы после «джава».
    """
    if not text or not replacements:
        return text

    for source in sorted(replacements, key=len, reverse=True):
        target = replacements[source]
        if not source.strip():
            continue
        # Границы подбираем под сам ключ: "\b" совпадает только рядом
        # со словесным символом, поэтому для ключей вроде "c++" на краях
        # нужен просмотр вперёд и назад — иначе замена молча не срабатывает.
        left = r"\b" if _is_word_char(source[0]) else r"(?<!\w)"
        right = r"\b" if _is_word_char(source[-1]) else r"(?!\w)"
        pattern = re.compile(left + re.escape(source) + right, re.IGNORECASE)
        text = pattern.sub(target.replace("\\", "\\\\"), text)
    return text


def strip_hallucinations(text: str) -> str:
    """Убирает строки, целиком состоящие из типичных галлюцинаций Whisper."""
    if not text:
        return text
    kept = [line for line in text.splitlines() if not _HALLUCINATION_RE.match(line)]
    return "\n".join(kept)


def normalize_whitespace(text: str) -> str:
    """Косметика пробелов и заглавной буквы в начале."""
    if not text:
        return text

    text = _SPACE_BEFORE_PUNCT.sub(r"\1", text)
    text = _SPACE_AFTER_OPEN.sub(r"\1", text)
    text = _MULTISPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = text.strip()

    # Заглавную ставим только для кириллицы. Латиницу трогать нельзя:
    # диктовка часто начинается с команды или имени пакета, а «npm install»,
    # превращённый в «Npm install», перестанет работать при вставке в терминал.
    if text and text[0].islower() and _CYRILLIC_LOWER.match(text[0]):
        text = text[0].upper() + text[1:]
    return text


def postprocess(text: str, replacements: dict[str, str] | None = None) -> str:
    """Полный проход: чистка, замены, косметика."""
    text = strip_hallucinations(text)
    text = apply_replacements(text, replacements or {})
    return normalize_whitespace(text)
