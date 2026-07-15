from pathlib import Path

from speedytype.secrets_store import SecretResolution


def test_isolated_fallback_mutates_only_fake_username_and_temp_env(tmp_path, monkeypatch):
    from scripts import verify_keyring_live

    mutated_usernames = []
    env_paths = []
    stored = {}

    def username_for(env_name, key_names):
        username = key_names[env_name]
        mutated_usernames.append(username)
        return username

    def fake_set(env_name, value, **kwargs):
        stored[username_for(env_name, kwargs["key_names"])] = value

    def fake_get(env_name, **kwargs):
        return stored.get(kwargs["key_names"][env_name], "")

    def fake_delete(env_name, **kwargs):
        stored.pop(username_for(env_name, kwargs["key_names"]), None)

    def fake_resolve(env_path, file_values, environment, **kwargs):
        env_paths.append(Path(env_path).resolve())
        fake_set("OPENAI_API_KEY", file_values["OPENAI_API_KEY"], **kwargs)
        return SecretResolution({"OPENAI_API_KEY": file_values["OPENAI_API_KEY"]})

    monkeypatch.setattr(verify_keyring_live, "set_api_key", fake_set)
    monkeypatch.setattr(verify_keyring_live, "get_api_key", fake_get)
    monkeypatch.setattr(verify_keyring_live, "delete_api_key", fake_delete)
    monkeypatch.setattr(verify_keyring_live, "resolve_api_keys", fake_resolve)

    assert verify_keyring_live.run_isolated_fallback_check(tmp_path) is True
    assert mutated_usernames
    assert set(mutated_usernames) == {"fallback_test_api_key"}
    assert env_paths
    assert all(path.is_relative_to(tmp_path.resolve()) for path in env_paths)


def test_production_verifier_does_not_print_exception_text(tmp_path, monkeypatch, capsys):
    from scripts import verify_keyring_live

    sentinel_secret = "SECRET-SENTINEL-MUST-NOT-APPEAR"
    monkeypatch.setattr(
        verify_keyring_live,
        "load_config",
        lambda path: (_ for _ in ()).throw(RuntimeError(f"failure contains {sentinel_secret}")),
    )

    ok, config = verify_keyring_live.verify_production_credentials(tmp_path / ".env")

    assert ok is False
    assert config is None
    assert sentinel_secret not in capsys.readouterr().out
