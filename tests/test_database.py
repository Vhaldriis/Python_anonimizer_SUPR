import pytest

from app.database import parse_db_url


def test_parse_db_url_basic():
    assert parse_db_url("postgresql://app_user:secret@localhost:5432/claude_anonimizer") == {
        "user": "app_user",
        "password": "secret",
        "host": "localhost",
        "port": 5432,
        "database": "claude_anonimizer",
    }


def test_parse_db_url_default_port_and_encoded_password():
    params = parse_db_url("postgresql://u:p%40ss%3Aw@db.local/d")
    assert params["password"] == "p@ss:w"
    assert params["port"] == 5432


@pytest.mark.parametrize("url", ["", "mysql://u:p@h:1/d", "postgresql://h:5432/d", "postgresql://u:p@h:5432/"])
def test_parse_db_url_invalid(url):
    with pytest.raises(ValueError):
        parse_db_url(url)


def test_parse_db_url_error_does_not_leak_password():
    with pytest.raises(ValueError) as exc:
        parse_db_url("postgresql://user:TopSecret@host:notaport/db")
    assert "TopSecret" not in str(exc.value)
