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

# Паттерны поиска персональных данных (функция Б)
PATTERNS = {
    "email": r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}",
    "phone": r"(?:\+?7|8)\s*\(?\d{3}\)?[\s\-]?\d{3}[\s\-]?\d{2}[\s\-]?\d{2}",
    "inn": r"\b\d{10,12}\b",
    "name": r"\b[А-ЯЁ][а-яё]+\s[А-ЯЁ][а-яё]+\b",
    "company": r"\b(?:ООО|ЗАО|ОАО|ПАО|ИП|АО)\s+[^\s,.;!]+(?:\s+[^\s,.;!]+)?",
}

COMPILED_PATTERNS = {ft: re.compile(pat) for ft, pat in PATTERNS.items()}

# Тип сущности Bitrix24 (custom_entities.entity_type) -> тип поля псевдонима
ENTITY_FIELD_TYPES = {"company": "company", "contact": "name"}

# Оригинал может сам содержать псевдоним (regex-этапы идут последовательно),
# поэтому обратная подстановка повторяется до стабилизации текста
MAX_DEANONYMIZE_PASSES = 10


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
        if not name or name not in result:
            continue
        # Псевдоним выдаётся в карте текущей сессии: глобальные псевдонимы Bitrix24
        # ([ОРГ_1], [ИМЯ_1], ...) совпадали бы с сессионными от regex-этапа
        field_type = ENTITY_FIELD_TYPES.get(ent.get("entity_type"), "other")
        pseudonym = get_or_create_pseudonym(name, field_type, user_id, session_id)
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
    Используется только карта пользовательской сессии (в неё же попадают
    сущности Bitrix24, встретившиеся в сообщениях этой сессии).
    """
    if not text:
        return text

    mapping = get_full_map(user_id, session_id)
    if not mapping:
        return text

    # Сортируем псевдонимы по длине (от длинных к коротким)
    sorted_map = sorted(mapping, key=lambda x: len(x["pseudonym"]), reverse=True)

    result = text
    for _ in range(MAX_DEANONYMIZE_PASSES):
        previous = result
        for item in sorted_map:
            result = result.replace(item["pseudonym"], item["original"])
        if result == previous:
            break

    return result


def extract_field_type(pseudonym: str) -> str:
    """Определяет тип поля по префиксу псевдонима: [ИМЯ_1] -> name."""
    for field_type, prefix in PSEUDONYM_PREFIXES.items():
        if pseudonym.startswith(f"[{prefix}_"):
            return field_type
    return "other"
