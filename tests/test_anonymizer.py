from app.anonymizer import anonymize_text, deanonymize_text


def roundtrip(text, user_id=1, session_id="s"):
    safe = anonymize_text(text, user_id, session_id)
    return safe, deanonymize_text(safe, user_id, session_id)


def test_readme_example_is_anonymized_and_restored(store):
    text = "Здравствуйте, я Иван Иванов из ООО 'Техно', телефон +7 999 123 45 67"
    safe, restored = roundtrip(text)
    assert safe == "Здравствуйте, я [ИМЯ_1] из [ОРГ_1], телефон [TEL_1]"
    assert restored == text


def test_email_and_inn(store):
    safe, restored = roundtrip("Почта ivan@company.ru, ИНН 7707083893")
    assert safe == "Почта [EMAIL_1], ИНН [ИНН_1]"
    assert restored == "Почта ivan@company.ru, ИНН 7707083893"


def test_same_value_gets_same_pseudonym(store):
    safe = anonymize_text("ivan@company.ru и снова ivan@company.ru", 1, "s")
    assert safe == "[EMAIL_1] и снова [EMAIL_1]"


def test_sessions_are_isolated(store):
    anonymize_text("ivan@company.ru", 1, "a")
    assert deanonymize_text("[EMAIL_1]", 1, "b") == "[EMAIL_1]"
    assert deanonymize_text("[EMAIL_1]", 2, "a") == "[EMAIL_1]"


def test_nested_pseudonym_is_fully_restored(store):
    # regex "name" срабатывает раньше "company": оригинал [ОРГ_1] = "ООО [ИМЯ_1]"
    text = "Договор с ООО Ромашка Плюс подписан"
    safe, restored = roundtrip(text)
    assert "Ромашка" not in safe
    assert restored == text


def test_bitrix_entity_does_not_collide_with_regex_pseudonym(store):
    # Глобальный псевдоним Bitrix24 и сессионный от regex раньше оба были [ОРГ_1]
    store.add_entity("company", "Газпром", "[ОРГ_1]")
    text = "Газпром и ООО Техно, договор"
    safe, restored = roundtrip(text)
    assert safe == "[ОРГ_1] и [ОРГ_2], договор"
    assert restored == text


def test_bitrix_contact_uses_name_prefix(store):
    store.add_entity("contact", "Петров Пётр", "[ИМЯ_1]")
    safe, restored = roundtrip("Звонил Петров Пётр")
    assert safe == "Звонил [ИМЯ_1]"
    assert restored == "Звонил Петров Пётр"


def test_unknown_pseudonym_in_answer_is_left_untouched(store):
    # Псевдоним, которого нет в карте сессии, не должен подменяться чужой сущностью
    store.add_entity("company", "Газпром", "[ОРГ_7]")
    assert deanonymize_text("Компания [ОРГ_7]", 1, "s") == "Компания [ОРГ_7]"


def test_empty_text(store):
    assert anonymize_text("", 1, "s") == ""
    assert deanonymize_text("", 1, "s") == ""
