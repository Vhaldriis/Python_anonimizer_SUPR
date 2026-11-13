import re
from typing import List, Dict, Optional
from app.database import (
    get_or_create_pseudonym,
    get_original,
    get_full_map,
    clear_map,
    get_all_entities,
    PSEUDONYM_PREFIXES,
)
from app.bitrix24_sync import GLOBAL_USER_ID, GLOBAL_SESSION

# Паттерны поиска персональных данных (функция Б)
PATTERNS = {
    "email": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone": r"(?:\+?7|8)\s*\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
    "inn": r"\b\d{10,12}\b",
    "name": r"\b[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\b",
    "company": r"\b(?:ООО|ЗАО|ОАО|ПАО|ИП|АО)\s+[^\s,.;!]+(?:\s+[^\s,.;!]+)?",
}

COMPILED_PATTERNS = {ft: re.compile(pat) for ft, pat in PATTERNS.items()}


# ============================================================
# Функция А: замена известных сущностей из БД (Bitrix24)
# ============================================================
def _replace_known_entities(text: str, user_id: int, session_id: str) -> str:
    """
    Ищет в тексте известные названия компаний и контактов из Bitrix24
    (хранятся в таблице custom_entities) и заменяет их на псевдонимы.
    """
    if not text:
        return text

    entities = get_all_entities()
    # Сортируем по длине (от длинных к коротким), чтобы не перекрывать частичные совпадения
    entities_sorted = sorted(entities, key=lambda x: len(x["name"]), reverse=True)

    result = text
    for ent in entities_sorted:
        name = ent["name"]
        pseudonym = ent["pseudonym"]
        if name and pseudonym and name in result:
            result = result.replace(name, pseudonym)

    return result


# ============================================================
# Функция Б: замена персональных данных по паттернам regex
# ============================================================
def _replace_regex_personal_data(text: str, user_id: int, session_id: str) -> str:
    """
    Ищет в тексте персональные данные по регулярным выражениям
    (email, телефон, ИНН, имя, компания) и заменяет на псевдонимы с уникальными номерами.
    """
    if not text:
        return text

    result = text

    for field_type, pattern in COMPILED_PATTERNS.items():

        def replacer(match, ft=field_type):
            original = match.group(0)
            pseudonym = get_or_create_pseudonym(original, ft, user_id, session_id)
            return pseudonym

        result = pattern.sub(replacer, result)

    return result


# ============================================================
# Основная функция анонимизации (А + Б)
# ============================================================
def anonymize_text(
    text: str,
    user_id: int,
    session_id: str,
) -> str:
    """
    Основная функция обезличивания.
    Порядок:
      1. Функция А — замена известных сущностей из БД (Bitrix24) на псевдонимы.
      2. Функция Б — замена остальных персональных данных по regex-паттернам.
    """
    if not text:
        return text

    result = text
    # Сначала известные сущности из Bitrix24 (БД)
    result = _replace_known_entities(result, user_id, session_id)
    # Затем regex-паттерны для остальных персональных данных
    result = _replace_regex_personal_data(result, user_id, session_id)

    return result


# ============================================================
# Деанимизация (восстановление в ответе ИИ)
# ============================================================
def deanonymize_text(
    text: str,
    user_id: int,
    session_id: str,
) -> str:
    """
    Заменяет псевдонимы в ответе на реальные значения из локальной БД.
    Загружает карту из пользовательской сессии + глобальных сущностей Bitrix24.
    """
    if not text:
        return text

    # Карта пользовательской сессии
    mapping = get_full_map(user_id, session_id)

    # Глобальные сущности Bitrix24 (псевдонимы компаний и контактов)
    global_mapping = get_full_map(GLOBAL_USER_ID, GLOBAL_SESSION)
    mapping.extend(global_mapping)

    if not mapping:
        return text

    # Сортируем псевдонимы по длине (от длинных к коротким)
    sorted_map = sorted(mapping, key=lambda x: len(x["pseudonym"]), reverse=True)

    result = text
    for item in sorted_map:
        result = result.replace(item["pseudonym"], item["original"])

    return result


def extract_field_type(pseudonym: str) -> str:
    """Определяет тип поля по префиксу псевдонима: [ИМЯ_1] -> name."""
    for field_type, prefix in PSEUDONYM_PREFIXES.items():
        if pseudonym.startswith(f"[{prefix}_"):
            return field_type
    return "other"
