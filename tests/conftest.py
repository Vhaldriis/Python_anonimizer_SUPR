"""Общие фикстуры: карта псевдонимов в памяти вместо PostgreSQL."""
import pytest

from app import anonymizer
from app.database import PSEUDONYM_PREFIXES


class FakeStore:
    """Повторяет контракт функций app.database, которые использует анонимайзер."""

    def __init__(self):
        self.rows = []       # (user_id, session_id, pseudonym, original, field_type)
        self.counters = {}   # (user_id, session_id, field_type) -> int
        self.entities = []   # custom_entities

    def get_or_create_pseudonym(self, original, field_type, user_id, session_id):
        for u, s, pseudonym, orig, _ in self.rows:
            if (u, s, orig) == (user_id, session_id, original):
                return pseudonym
        key = (user_id, session_id, field_type)
        self.counters[key] = self.counters.get(key, 0) + 1
        prefix = PSEUDONYM_PREFIXES.get(field_type, "ДАННЫЕ")
        pseudonym = f"[{prefix}_{self.counters[key]}]"
        self.rows.append((user_id, session_id, pseudonym, original, field_type))
        return pseudonym

    def get_full_map(self, user_id, session_id):
        return [
            {"pseudonym": p, "original": o, "field_type": ft}
            for u, s, p, o, ft in self.rows
            if (u, s) == (user_id, session_id)
        ]

    def get_all_entities(self):
        return list(self.entities)

    def add_entity(self, entity_type, name, pseudonym):
        self.entities.append(
            {"entity_type": entity_type, "entity_id_external": str(len(self.entities) + 1),
             "name": name, "pseudonym": pseudonym}
        )


@pytest.fixture
def store(monkeypatch):
    fake = FakeStore()
    monkeypatch.setattr(anonymizer, "get_or_create_pseudonym", fake.get_or_create_pseudonym)
    monkeypatch.setattr(anonymizer, "get_full_map", fake.get_full_map)
    monkeypatch.setattr(anonymizer, "get_all_entities", fake.get_all_entities)
    return fake
