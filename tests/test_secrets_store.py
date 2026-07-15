import pytest

from speedytype import secrets_store


def install_fake_backend(monkeypatch, initial=None, fail_set=False):
    values = dict(initial or {})
    monkeypatch.setattr(
        secrets_store,
        "_get_password",
        lambda service, user: values.get((service, user)),
    )

    def set_password(service, user, value):
        if fail_set:
            raise RuntimeError("backend locked")
        values[(service, user)] = value

    monkeypatch.setattr(secrets_store, "_set_password", set_password)
    monkeypatch.setattr(
        secrets_store,
        "_delete_password",
        lambda service, user: values.pop((service, user), None),
    )
    return values


def test_set_api_key_verifies_round_trip(monkeypatch):
    values = install_fake_backend(monkeypatch)

    secrets_store.set_api_key("OPENAI_API_KEY", "sk-fake")

    assert values[("SpeedyType", "openai_api_key")] == "sk-fake"


def test_set_api_key_rejects_failed_readback(monkeypatch):
    monkeypatch.setattr(secrets_store, "_set_password", lambda *args: None)
    monkeypatch.setattr(secrets_store, "_get_password", lambda *args: "different")

    with pytest.raises(secrets_store.SecretStoreError, match="verification failed"):
        secrets_store.set_api_key("OPENAI_API_KEY", "sk-fake")


def test_delete_api_key_ignores_missing_credential(monkeypatch):
    def missing(*args):
        raise secrets_store.PasswordDeleteError("not found")

    monkeypatch.setattr(secrets_store, "_delete_password", missing)

    secrets_store.delete_api_key("MINIMAX_API_KEY")


def test_delete_api_key_reports_delete_error_when_credential_still_exists(monkeypatch):
    def failed_delete(*args):
        raise secrets_store.PasswordDeleteError("backend refused deletion")

    monkeypatch.setattr(secrets_store, "_delete_password", failed_delete)
    monkeypatch.setattr(secrets_store, "_get_password", lambda *args: "still-present")

    with pytest.raises(secrets_store.SecretStoreError, match="Credential deletion failed"):
        secrets_store.delete_api_key("OPENAI_API_KEY")


def test_resolve_prefers_keyring_over_environment_and_file(monkeypatch, tmp_path):
    install_fake_backend(
        monkeypatch,
        {("SpeedyType", "openai_api_key"): "ring-openai"},
    )

    result = secrets_store.resolve_api_keys(
        tmp_path / ".env",
        {"OPENAI_API_KEY": "file-openai"},
        environment={"OPENAI_API_KEY": "environment-openai"},
    )

    assert result.values["OPENAI_API_KEY"] == "ring-openai"
    assert result.migrated == ()


def test_resolve_uses_environment_without_migrating(monkeypatch, tmp_path):
    install_fake_backend(monkeypatch)

    result = secrets_store.resolve_api_keys(
        tmp_path / ".env",
        {"OPENAI_API_KEY": "file-openai"},
        environment={"OPENAI_API_KEY": "environment-openai"},
    )

    assert result.values["OPENAI_API_KEY"] == "environment-openai"
    assert result.migrated == ()


def test_resolve_migrates_file_value_and_removes_only_verified_line(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "# keep\nOPENAI_API_KEY=sk-fake\nGEMINI_API_KEY=gem-fake\nLLM_PROVIDER=gemini\n",
        encoding="utf-8",
    )

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

    result = secrets_store.resolve_api_keys(
        env_path,
        {"OPENAI_API_KEY": "sk-fake"},
        environment={},
    )

    assert result.values["OPENAI_API_KEY"] == "sk-fake"
    assert result.migrated == ()
    assert result.warnings and "RuntimeError" in result.warnings[0]
    assert env_path.read_text(encoding="utf-8") == original


def test_backend_exception_text_never_reaches_resolution_warning(tmp_path, monkeypatch):
    sentinel_secret = "SECRET-SENTINEL-MUST-NOT-APPEAR"

    def fail_read(*args):
        raise RuntimeError(f"backend included {sentinel_secret}")

    monkeypatch.setattr(secrets_store, "_get_password", fail_read)

    result = secrets_store.resolve_api_keys(
        tmp_path / ".env",
        {},
        environment={},
    )

    assert result.warnings
    assert "RuntimeError" in " ".join(result.warnings)
    assert sentinel_secret not in " ".join(result.warnings)


def test_remove_env_keys_preserves_comments_blank_lines_and_crlf(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch)
    env_path = tmp_path / ".env"
    original = b"# OPENAI_API_KEY=commented\r\n\r\nOPENAI_API_KEY=sk-fake\r\nMODE=fast\r\n"
    env_path.write_bytes(original)

    secrets_store.resolve_api_keys(
        env_path,
        {"OPENAI_API_KEY": "sk-fake"},
        environment={},
    )

    assert env_path.read_bytes() == b"# OPENAI_API_KEY=commented\r\n\r\nMODE=fast\r\n"
