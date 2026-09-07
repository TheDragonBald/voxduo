"""Тесты постобработки расшифровки.

Главный риск здесь — переусердствовать: замены не должны трогать части других
слов, а чистка галлюцинаций не должна отрезать настоящую речь.
"""

from __future__ import annotations

import pytest

from voxduo.stt import postprocess as pp

# --- словарь замен ---

def test_replacement_basic():
    assert pp.apply_replacements("пишу на джаваскрипт", {"джаваскрипт": "JavaScript"}) == (
        "пишу на JavaScript"
    )


def test_replacement_is_case_insensitive():
    result = pp.apply_replacements("Джаваскрипт и ДЖАВАСКРИПТ", {"джаваскрипт": "JavaScript"})
    assert result == "JavaScript и JavaScript"


def test_replacement_does_not_touch_parts_of_words():
    """«питончик» — это не «Python»чик."""
    assert pp.apply_replacements("питончик", {"питон": "Python"}) == "питончик"


def test_longer_keys_win():
    """Иначе «джава скрипт» никогда не сработает после «джава»."""
    replacements = {"джава": "Java", "джава скрипт": "JavaScript"}
    assert pp.apply_replacements("пишу на джава скрипт", replacements) == "пишу на JavaScript"


def test_replacement_handles_empty_input():
    assert pp.apply_replacements("", {"а": "б"}) == ""
    assert pp.apply_replacements("текст", {}) == "текст"


def test_replacement_ignores_blank_key():
    assert pp.apply_replacements("текст", {"   ": "X"}) == "текст"


def test_replacement_with_regex_special_chars():
    """Ключ со спецсимволами регулярок не должен ломать замену."""
    assert pp.apply_replacements("версия c++", {"c++": "C++"}) == "версия C++"


# --- галлюцинации ---

@pytest.mark.parametrize(
    "line",
    [
        "Продолжение следует...",
        "продолжение следует",
        "Субтитры сделал DimaTorzok",
        "Субтитры создавал DimaTorzok",
        "Редактор субтитров А.Синецкая",
        "Спасибо за просмотр!",
        "Подписывайтесь на канал!",
    ],
)
def test_hallucinations_removed_when_whole_line(line):
    assert pp.strip_hallucinations(line).strip() == ""


def test_real_speech_is_not_cut():
    """Фраза внутри живой речи — не галлюцинация."""
    text = "Я сказал спасибо за просмотр коллеге, он помог"
    assert pp.strip_hallucinations(text) == text


def test_hallucination_removed_only_its_own_line():
    text = "Первая мысль\nПродолжение следует...\nВторая мысль"
    assert pp.strip_hallucinations(text) == "Первая мысль\nВторая мысль"


def test_strip_hallucinations_empty():
    assert pp.strip_hallucinations("") == ""


# --- нормализация ---

def test_space_before_punctuation_removed():
    assert pp.normalize_whitespace("привет , мир !") == "Привет, мир!"


def test_multiple_spaces_collapsed():
    assert pp.normalize_whitespace("слово    другое") == "Слово другое"


def test_first_letter_capitalized():
    assert pp.normalize_whitespace("короче, всё готово") == "Короче, всё готово"


def test_latin_identifier_at_start_untouched():
    """npm не должен стать Npm: вставленная в терминал команда перестанет работать."""
    assert pp.normalize_whitespace("npm install") == "npm install"
    assert pp.normalize_whitespace("git push origin main") == "git push origin main"


def test_digit_at_start_untouched():
    assert pp.normalize_whitespace("42 попугая") == "42 попугая"


def test_normalize_empty():
    assert pp.normalize_whitespace("") == ""
    assert pp.normalize_whitespace("   ") == ""


# --- всё вместе ---

def test_full_pipeline():
    raw = "  джаваскрипт  упал  на  линтере , надо чинить\nПродолжение следует...  "
    result = pp.postprocess(raw, {"джаваскрипт": "JavaScript"})
    assert result == "JavaScript упал на линтере, надо чинить"


def test_full_pipeline_on_silence_result():
    """Тишина, на которой Whisper нафантазировал, должна дать пустоту."""
    assert pp.postprocess("Продолжение следует...", {}) == ""
