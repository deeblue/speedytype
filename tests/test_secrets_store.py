from pathlib import Path

import pytest

from speedytype import secrets_store


def install_fake_backend(monkeypatch, initial=None, fail_set=False):
    values = dict(initial or {})
    monkeypatch.setattr(secrets_store, "_get_password", lambda service, user: values.get((service, user)))

    def set_password(service, user, value):
        if fail_set:
            raise RuntimeError("backend locked")
        values[(service, user)] = value

    monkeypatch.setattr(secrets_store, "_set_password", set_password)
    monkeypatch.setattr(secrets_store, "_delete_password", lambda service, user: values.pop((service, user), None))
    return values


def test_set_api_key_verifies_round_trip(monkeypatch):
    values = install_fake_backend(monkeypatch)
    secrets_store.set_api_key("OPENAI_API_KEY", "sk-fake")
    assert values[("SpeedyType", "openai_api_key")] == "sk-fake"


def test_resolve_migrates_file_value_and_removes_only_verified_line(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text("# keep\nOPENAI_API_KEY=sk-fake\nGEMINI_API_KEY=gem-fake\nLLM_PROVIDER=gemini\n", encoding="utf-8")
    result = secrets_store.resolve_api_keys(
        env_path,
        {"OPENAI_API_KEY": "sk-fake", "GEMINI_API_KEY": "gem-fake"},
        environment={},
    )
    assert result.values["OPENAI_API_KEY"] == "sk-fake"
    assert result.migrated == ("OPENAI_API_KEY", "GEMINI_API_KEY")
    assert env_path.read_text(encoding="utf-8") == "# keep\nLLM_PROVIDER=gemini\n"


def test_failed_write_keeps_env_exactly(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch, fail_set=True)
    env_path = tmp_path / ".env"
    original = "# keep\nOPENAI_API_KEY=sk-fake\n"
    env_path.write_text(original, encoding="utf-8")
    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": "sk-fake"}, environment={})
    assert result.values["OPENAI_API_KEY"] == "sk-fake"
    assert result.migrated == ()
    assert result.warnings and "backend locked" in result.warnings[0]
    assert env_path.read_text(encoding="utf-8") == original
