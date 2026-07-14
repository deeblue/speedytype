from contextlib import contextmanager
import os
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
    assert result.warnings and "RuntimeError" in result.warnings[0]
    assert "backend locked" not in result.warnings[0]
    assert env_path.read_text(encoding="utf-8") == original


def test_read_back_mismatch_keeps_env_exactly(tmp_path, monkeypatch):
    written = False

    def get_password(service, user):
        return "wrong-value" if written else None

    def set_password(service, user, value):
        nonlocal written
        written = True

    monkeypatch.setattr(secrets_store, "_get_password", get_password)
    monkeypatch.setattr(secrets_store, "_set_password", set_password)
    env_path = tmp_path / ".env"
    original = "OPENAI_API_KEY=sk-fake\n"
    env_path.write_text(original, encoding="utf-8")

    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": "sk-fake"}, environment={})

    assert result.migrated == ()
    assert result.warnings == ("Credential verification failed for OPENAI_API_KEY",)
    assert env_path.read_text(encoding="utf-8") == original


def test_migration_removes_only_effective_matching_duplicate(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_text(
        "OPENAI_API_KEY=sk-old\nOPENAI_API_KEY='sk-fake'\nLLM_PROVIDER=gemini\n",
        encoding="utf-8",
    )

    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": "sk-fake"}, environment={})

    assert result.migrated == ("OPENAI_API_KEY",)
    assert result.warnings == ()
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-old\nLLM_PROVIDER=gemini\n"


def test_changed_env_value_is_not_scrubbed_after_verified_write(tmp_path, monkeypatch):
    values = {}
    env_path = tmp_path / ".env"
    env_path.write_text("OPENAI_API_KEY=sk-parsed\n", encoding="utf-8")
    monkeypatch.setattr(secrets_store, "_get_password", lambda service, user: values.get((service, user)))

    def set_password(service, user, value):
        values[(service, user)] = value
        env_path.write_text("OPENAI_API_KEY=sk-changed\n", encoding="utf-8")

    monkeypatch.setattr(secrets_store, "_set_password", set_password)

    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": "sk-parsed"}, environment={})

    assert result.migrated == ("OPENAI_API_KEY",)
    assert result.warnings == ("Environment file scrub skipped for OPENAI_API_KEY: source changed",)
    assert env_path.read_text(encoding="utf-8") == "OPENAI_API_KEY=sk-changed\n"


def test_backend_exception_text_is_redacted_from_error_and_warning(tmp_path, monkeypatch):
    credential = "sk-secret-in-backend-error"
    monkeypatch.setattr(secrets_store, "_get_password", lambda service, user: None)

    def set_password(service, user, value):
        raise RuntimeError(f"could not store {value}")

    monkeypatch.setattr(secrets_store, "_set_password", set_password)

    with pytest.raises(secrets_store.SecretStoreError) as caught:
        secrets_store.set_api_key("OPENAI_API_KEY", credential)
    assert str(caught.value) == "Credential store set failed for OPENAI_API_KEY (RuntimeError)"
    assert credential not in str(caught.value)

    env_path = tmp_path / ".env"
    env_path.write_text(f"OPENAI_API_KEY={credential}\n", encoding="utf-8")
    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": credential}, environment={})
    assert result.warnings == ("Credential store set failed for OPENAI_API_KEY (RuntimeError)",)
    assert all(credential not in warning for warning in result.warnings)


def test_env_rewrite_occurs_while_exclusive_lock_is_held(tmp_path, monkeypatch):
    install_fake_backend(monkeypatch)
    env_path = tmp_path / ".env"
    env_path.write_bytes(b"OPENAI_API_KEY=sk-fake\r\nLLM_PROVIDER=gemini\r\n")
    lock_state = {"held": False}

    @contextmanager
    def fake_exclusive_file_lock(env_file):
        lock_state["held"] = True
        try:
            yield
        finally:
            lock_state["held"] = False

    monkeypatch.setattr(secrets_store, "_exclusive_file_lock", fake_exclusive_file_lock, raising=False)
    real_path_open = Path.open

    class TrackingFile:
        def __init__(self, env_file):
            self._env_file = env_file

        def __enter__(self):
            self._env_file.__enter__()
            return self

        def __exit__(self, *args):
            return self._env_file.__exit__(*args)

        def write(self, value):
            assert lock_state["held"], "environment file write occurred without the exclusive lock"
            return self._env_file.write(value)

        def truncate(self, *args):
            assert lock_state["held"], "environment file truncate occurred without the exclusive lock"
            return self._env_file.truncate(*args)

        def __getattr__(self, name):
            return getattr(self._env_file, name)

    def tracking_open(path, *args, **kwargs):
        return TrackingFile(real_path_open(path, *args, **kwargs))

    monkeypatch.setattr(Path, "open", tracking_open)

    result = secrets_store.resolve_api_keys(env_path, {"OPENAI_API_KEY": "sk-fake"}, environment={})

    assert result.warnings == ()
    assert lock_state["held"] is False
    assert env_path.read_bytes() == b"LLM_PROVIDER=gemini\r\n"


@pytest.mark.skipif(os.name != "nt", reason="Windows locking contract")
def test_windows_lock_covers_fixed_range_beyond_eof(tmp_path, monkeypatch):
    import msvcrt

    env_path = tmp_path / ".env"
    env_path.write_bytes(b"KEY=x\n")
    file_size = env_path.stat().st_size
    locking_calls = []
    monkeypatch.setattr(
        msvcrt,
        "locking",
        lambda file_descriptor, mode, byte_count: locking_calls.append((mode, byte_count)),
    )

    with env_path.open("r+", encoding="utf-8", newline="") as env_file:
        with secrets_store._exclusive_file_lock(env_file):
            pass

    expected_range = 0x7FFFFFFF
    assert locking_calls == [
        (msvcrt.LK_LOCK, expected_range),
        (msvcrt.LK_UNLCK, expected_range),
    ]
    assert expected_range > file_size
    assert getattr(secrets_store, "ENV_LOCK_RANGE_BYTES", None) == expected_range
