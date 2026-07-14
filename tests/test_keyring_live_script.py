from pathlib import Path
from types import SimpleNamespace

from scripts import verify_keyring_live


def test_isolated_fallback_mutates_only_test_username_and_uses_temp_env(tmp_path, monkeypatch):
    mutations: list[tuple[str, str]] = []
    env_paths: list[Path] = []
    stored: dict[str, str] = {}

    def fake_set(env_name, value, *, service_name, key_names):
        username = key_names[env_name]
        mutations.append(("set", username))
        stored[username] = value

    def fake_get(env_name, *, service_name, key_names):
        return stored.get(key_names[env_name])

    def fake_delete(env_name, *, service_name, key_names):
        username = key_names[env_name]
        mutations.append(("delete", username))
        stored.pop(username, None)

    def fake_resolve(env_path, file_values, environment, service_name, key_names):
        path = Path(env_path).resolve()
        env_paths.append(path)
        return verify_keyring_live.SecretResolution(dict(file_values))

    monkeypatch.setattr(verify_keyring_live, "set_api_key", fake_set)
    monkeypatch.setattr(verify_keyring_live, "get_api_key", fake_get)
    monkeypatch.setattr(verify_keyring_live, "delete_api_key", fake_delete)
    monkeypatch.setattr(verify_keyring_live, "resolve_api_keys", fake_resolve)

    assert verify_keyring_live.verify_isolated_fallback(tmp_path)
    assert mutations
    assert {username for _, username in mutations} == {"fallback_test_api_key"}
    assert env_paths
    assert all(path.is_relative_to(tmp_path.resolve()) for path in env_paths)


def test_delete_guard_rejects_any_non_test_username(monkeypatch):
    deleted = []
    monkeypatch.setattr(
        verify_keyring_live,
        "delete_api_key",
        lambda *args, **kwargs: deleted.append((args, kwargs)),
    )

    try:
        verify_keyring_live._delete_fallback({"OPENAI_API_KEY": "openai_api_key"})
    except AssertionError:
        pass
    else:
        raise AssertionError("production username passed the delete guard")

    assert deleted == []


def test_isolated_fallback_fails_when_final_cleanup_cannot_be_verified(tmp_path, monkeypatch):
    deletes = 0
    monkeypatch.setattr(verify_keyring_live, "set_api_key", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda *args, **kwargs: verify_keyring_live.FALLBACK_VALUE,
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "resolve_api_keys",
        lambda *args, **kwargs: verify_keyring_live.SecretResolution(
            {"OPENAI_API_KEY": verify_keyring_live.FALLBACK_VALUE}
        ),
    )

    def fail_final_delete(*args, **kwargs):
        nonlocal deletes
        deletes += 1
        if deletes == 2:
            raise verify_keyring_live.SecretStoreError("cleanup failed")

    monkeypatch.setattr(verify_keyring_live, "delete_api_key", fail_final_delete)

    assert not verify_keyring_live.verify_isolated_fallback(tmp_path)


def test_live_verification_reports_status_without_printing_complete_values(
    tmp_path, monkeypatch, capsys
):
    secrets = {
        "OPENAI_API_KEY": "openai-complete-secret",
        "GEMINI_API_KEY": "gemini-complete-secret",
        "MINIMAX_API_KEY": "minimax-complete-secret",
    }
    config = SimpleNamespace(
        openai_api_key=secrets["OPENAI_API_KEY"],
        gemini_api_key=secrets["GEMINI_API_KEY"],
        minimax_api_key=secrets["MINIMAX_API_KEY"],
    )
    loaded_paths = []
    read_names = []

    monkeypatch.setattr(
        verify_keyring_live,
        "load_config",
        lambda path: loaded_paths.append(Path(path)) or config,
    )

    def fake_get(env_name, *, service_name, key_names):
        read_names.append((env_name, key_names[env_name]))
        return secrets[env_name]

    monkeypatch.setattr(verify_keyring_live, "get_api_key", fake_get)
    monkeypatch.setattr(
        verify_keyring_live,
        "test_openai_key",
        lambda value: (False, f"request failed for {value}"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "test_gemini_key",
        lambda value: (True, f"connected with {value}"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "test_minimax_key",
        lambda value: (True, f"connected with {value}"),
    )
    monkeypatch.setattr(verify_keyring_live, "verify_isolated_fallback", lambda root: True)

    real_env = tmp_path / "real.env"
    verify_keyring_live.run_live_verification(real_env, tmp_path)

    output = capsys.readouterr().out
    assert loaded_paths == [real_env]
    assert read_names == [
        ("OPENAI_API_KEY", "openai_api_key"),
        ("GEMINI_API_KEY", "gemini_api_key"),
        ("MINIMAX_API_KEY", "minimax_api_key"),
    ]
    assert all(secret not in output for secret in secrets.values())
    assert "exists=PASS" in output
    assert "matches_resolved=PASS" in output


def test_live_verification_allows_optional_minimax_key_to_be_absent(tmp_path, monkeypatch):
    config = SimpleNamespace(
        openai_api_key="openai-secret",
        gemini_api_key="gemini-secret",
        minimax_api_key="",
    )
    stored = {
        "OPENAI_API_KEY": config.openai_api_key,
        "GEMINI_API_KEY": config.gemini_api_key,
        "MINIMAX_API_KEY": None,
    }
    monkeypatch.setattr(verify_keyring_live, "load_config", lambda path: config)
    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda env_name, **kwargs: stored[env_name],
    )
    monkeypatch.setattr(verify_keyring_live, "test_openai_key", lambda value: (True, "OK"))
    monkeypatch.setattr(verify_keyring_live, "test_gemini_key", lambda value: (True, "OK"))
    monkeypatch.setattr(
        verify_keyring_live,
        "test_minimax_key",
        lambda value: (_ for _ in ()).throw(AssertionError("optional provider was called")),
    )
    monkeypatch.setattr(verify_keyring_live, "verify_isolated_fallback", lambda root: True)

    assert verify_keyring_live.run_live_verification(tmp_path / "real.env", tmp_path)
