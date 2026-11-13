import os
import pg8000
from typing import Optional, List, Dict
from contextlib import contextmanager

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:2912@localhost:5432/claude_anonimizer",
)

# Префиксы псевдонимов по типам полей
PSEUDONYM_PREFIXES = {
    "email": "EMAIL",
    "phone": "TEL",
    "inn": "ИНН",
    "name": "ИМЯ",
    "company": "ОРГ",
    "other": "ДАННЫЕ",
}


def parse_db_url(url: str) -> dict:
    """Разбивает DATABASE_URL на параметры для pg8000."""
    # postgresql://user:password@host:port/dbname
    import re
    m = re.match(r"postgresql://([^:]+):([^@]+)@([^:]+):(\d+)/(.+)", url)
    if not m:
        raise ValueError(f"Неверный формат DATABASE_URL: {url}")
    return {
        "user": m.group(1),
        "password": m.group(2),
        "host": m.group(3),
        "port": int(m.group(4)),
        "database": m.group(5),
    }


@contextmanager
def get_conn():
    params = parse_db_url(DATABASE_URL)
    conn = pg8000.connect(**params)
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def get_cursor(commit: bool = False):
    with get_conn() as conn:
        with conn.cursor() as cur:
            yield cur
            if commit:
                conn.commit()


def init_db() -> None:
    """Создаёт таблицы, если они ещё не существуют."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username VARCHAR(100) NOT NULL UNIQUE,
                password_hash VARCHAR(255) NOT NULL,
                role VARCHAR(20) DEFAULT 'user',
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id VARCHAR(100) PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
                created_at TIMESTAMP DEFAULT NOW()
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS pseudonym_counters (
                user_id INTEGER NOT NULL,
                session_id VARCHAR(100) NOT NULL,
                field_type VARCHAR(50) NOT NULL,
                counter INTEGER DEFAULT 0,
                PRIMARY KEY (user_id, session_id, field_type)
            );
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS anonymization_map (
                id SERIAL PRIMARY KEY,
                user_id INTEGER NOT NULL,
                session_id VARCHAR(100) NOT NULL,
                pseudonym VARCHAR(255) NOT NULL,
                original TEXT NOT NULL,
                field_type VARCHAR(50) DEFAULT 'other',
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (user_id, session_id, pseudonym)
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_user_session ON anonymization_map(user_id, session_id);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_map_pseudonym ON anonymization_map(pseudonym);"
        )
    init_custom_entities_table()


def get_or_create_pseudonym(
    original: str,
    field_type: str,
    user_id: int,
    session_id: str,
) -> str:
    """
    Возвращает существующий псевдоним для оригинала или создаёт новый
    с уникальной числовой подписью (например, [ИМЯ_1], [ИМЯ_2]).
    """
    prefix = PSEUDONYM_PREFIXES.get(field_type, "ДАННЫЕ")

    with get_cursor(commit=True) as cur:
        # 1. Если такое оригинальное значение уже есть в карте — вернуть старый псевдоним
        cur.execute(
            """
            SELECT pseudonym FROM anonymization_map
            WHERE user_id = %s AND session_id = %s AND original = %s
            LIMIT 1
            """,
            (user_id, session_id, original),
        )
        row = cur.fetchone()
        if row:
            return row[0]

        # 2. Инкрементировать счётчик для типа поля
        cur.execute(
            """
            INSERT INTO pseudonym_counters (user_id, session_id, field_type, counter)
            VALUES (%s, %s, %s, 1)
            ON CONFLICT (user_id, session_id, field_type)
            DO UPDATE SET counter = pseudonym_counters.counter + 1
            RETURNING counter
            """,
            (user_id, session_id, field_type),
        )
        counter = cur.fetchone()[0]
        pseudonym = f"[{prefix}_{counter}]"

        # 3. Защита от коллизий псевдонима
        while True:
            try:
                cur.execute(
                    """
                    INSERT INTO anonymization_map
                    (user_id, session_id, pseudonym, original, field_type)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (user_id, session_id, pseudonym, original, field_type),
                )
                break
            except pg8000.IntegrityError:
                conn = cur.connection
                conn.rollback()
                cur.execute(
                    """
                    UPDATE pseudonym_counters
                    SET counter = counter + 1
                    WHERE user_id = %s AND session_id = %s AND field_type = %s
                    RETURNING counter
                    """,
                    (user_id, session_id, field_type),
                )
                counter = cur.fetchone()[0]
                pseudonym = f"[{prefix}_{counter}]"

    return pseudonym


def get_original(
    pseudonym: str,
    user_id: int,
    session_id: str,
) -> Optional[str]:
    """Восстанавливает оригинальное значение по псевдониму."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT original FROM anonymization_map
            WHERE user_id = %s AND session_id = %s AND pseudonym = %s
            LIMIT 1
            """,
            (user_id, session_id, pseudonym),
        )
        row = cur.fetchone()
        return row[0] if row else None


def get_full_map(user_id: int, session_id: str) -> List[Dict[str, str]]:
    """Возвращает все пары псевдоним -> оригинал для сессии."""
    with get_cursor() as cur:
        cur.execute(
            """
            SELECT pseudonym, original, field_type FROM anonymization_map
            WHERE user_id = %s AND session_id = %s
            ORDER BY id
            """,
            (user_id, session_id),
        )
        rows = cur.fetchall()
        return [{"pseudonym": r[0], "original": r[1], "field_type": r[2]} for r in rows]


def clear_map(user_id: int, session_id: str) -> None:
    """Очищает карту псевдонимов и счётчики для сессии."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            DELETE FROM anonymization_map
            WHERE user_id = %s AND session_id = %s
            """,
            (user_id, session_id),
        )
        cur.execute(
            """
            DELETE FROM pseudonym_counters
            WHERE user_id = %s AND session_id = %s
            """,
            (user_id, session_id),
        )


# ---------- Известные сущности Bitrix24 (компании, контакты и т.д.) ----------

def init_custom_entities_table() -> None:
    """Создаёт таблицу известных сущностей Bitrix24."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS custom_entities (
                id SERIAL PRIMARY KEY,
                entity_type VARCHAR(50) NOT NULL,
                entity_id_external VARCHAR(100) NOT NULL,
                name TEXT NOT NULL,
                pseudonym VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT NOW(),
                UNIQUE (entity_type, entity_id_external)
            );
            """
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_entities_name ON custom_entities(name);"
        )
        cur.execute(
            "CREATE INDEX IF NOT EXISTS idx_custom_entities_type ON custom_entities(entity_type);"
        )


def save_entity(entity_type: str, entity_id_external: str, name: str, pseudonym: str) -> None:
    """Сохраняет или обновляет сущность Bitrix24 с её псевдонимом."""
    with get_cursor(commit=True) as cur:
        cur.execute(
            """
            INSERT INTO custom_entities (entity_type, entity_id_external, name, pseudonym)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (entity_type, entity_id_external)
            DO UPDATE SET name = EXCLUDED.name, pseudonym = EXCLUDED.pseudonym
            """,
            (entity_type, entity_id_external, name, pseudonym),
        )


def get_all_entities() -> list[dict]:
    """Возвращает все известные сущности для построения паттернов анонимизации."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT entity_type, entity_id_external, name, pseudonym FROM custom_entities ORDER BY name DESC"
        )
        rows = cur.fetchall()
        return [
            {
                "entity_type": r[0],
                "entity_id_external": r[1],
                "name": r[2],
                "pseudonym": r[3],
            }
            for r in rows
        ]


def get_entity_pseudonym(name: str) -> Optional[str]:
    """Возвращает псевдоним по точному совпадению названия сущности."""
    with get_cursor() as cur:
        cur.execute(
            "SELECT pseudonym FROM custom_entities WHERE name = %s LIMIT 1",
            (name,),
        )
        row = cur.fetchone()
        return row[0] if row else None
