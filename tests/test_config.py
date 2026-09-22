import pytest

from weather_platform.config import get_db_settings, parse_dotenv
from weather_platform.db import build_connection_string


def test_parse_dotenv_ignores_comments_blank_lines_and_strips_quotes():
    text = "# ghi chú\n\nDB_SERVER=localhost\nDB_NAME = \"VNDataPlatform\"\nDB_USER='sa'\nkhong_hop_le\n"
    assert parse_dotenv(text) == {"DB_SERVER": "localhost", "DB_NAME": "VNDataPlatform", "DB_USER": "sa"}


def test_default_settings_use_windows_authentication():
    s = get_db_settings({})
    assert s.server == "localhost"
    assert s.database == "VNDataPlatform"
    assert s.trusted_connection is True
    assert s.trust_server_certificate is True


def test_settings_read_from_environment_mapping():
    s = get_db_settings({
        "DB_SERVER": r"PC\SQLEXPRESS", "DB_NAME": "Test", "DB_TRUSTED_CONNECTION": "no",
        "DB_USER": "u", "DB_PASSWORD": "p", "DB_TRUST_SERVER_CERTIFICATE": "false",
    })
    assert s.server == r"PC\SQLEXPRESS"
    assert s.trusted_connection is False
    assert s.trust_server_certificate is False


def test_connection_string_with_windows_authentication():
    cs = build_connection_string(get_db_settings({}))
    assert "DRIVER={ODBC Driver 18 for SQL Server}" in cs
    assert "SERVER=localhost" in cs
    assert "DATABASE=VNDataPlatform" in cs
    assert "Trusted_Connection=yes" in cs
    assert "TrustServerCertificate=yes" in cs
    assert "PWD" not in cs


def test_connection_string_with_sql_authentication():
    cs = build_connection_string(get_db_settings({
        "DB_TRUSTED_CONNECTION": "no", "DB_USER": "sa", "DB_PASSWORD": "secret"}))
    assert "UID=sa" in cs and "PWD=secret" in cs
    assert "Trusted_Connection" not in cs


def test_sql_authentication_requires_user():
    with pytest.raises(ValueError):
        build_connection_string(get_db_settings({"DB_TRUSTED_CONNECTION": "no"}))
