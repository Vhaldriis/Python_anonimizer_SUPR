-- Инициализация базы данных для Python-версии Claude Anonymizer
-- PostgreSQL

CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(20) DEFAULT 'user',
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS sessions (
    id VARCHAR(100) PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- Счётчики псевдонимов для уникальных числовых подписей: [ИМЯ_1], [ИМЯ_2], ...
CREATE TABLE IF NOT EXISTS pseudonym_counters (
    user_id INTEGER NOT NULL,
    session_id VARCHAR(100) NOT NULL,
    field_type VARCHAR(50) NOT NULL,
    counter INTEGER DEFAULT 0,
    PRIMARY KEY (user_id, session_id, field_type)
);

-- Карта псевдонимов: что отправили в Claude <-> реальное значение
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

CREATE INDEX IF NOT EXISTS idx_map_user_session ON anonymization_map(user_id, session_id);
CREATE INDEX IF NOT EXISTS idx_map_pseudonym ON anonymization_map(pseudonym);

-- Тестовый пользователь (логин: admin, пароль: admin123)
INSERT INTO users (username, password_hash, role)
VALUES ('admin', '$2b$12$K6Z7X9Y2W1Q4R5T6U8I0O1P3A5S7D9F0G1H2J3K4L5M6N7B8V9C0X1Z2', 'admin')
ON CONFLICT (username) DO NOTHING;
