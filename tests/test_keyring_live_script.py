from pathlib import Path
from types import SimpleNamespace

import pytest

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
        return verify_keyring_live.SecretResolution(
            dict(file_values), (verify_keyring_live.FALLBACK_ENV_NAME,)
        )

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

    with pytest.raises(RuntimeError, match="non-test credential"):
        verify_keyring_live._delete_fallback({"OPENAI_API_KEY": "openai_api_key"})

    assert deleted == []


def test_isolated_fallback_refuses_foreign_preexisting_value_without_mutation(tmp_path, monkeypatch):
    mutations = []
    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda *args, **kwargs: "foreign-value-that-must-not-be-touched",
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "set_api_key",
        lambda *args, **kwargs: mutations.append("set"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "delete_api_key",
        lambda *args, **kwargs: mutations.append("delete"),
    )

    with pytest.raises(RuntimeError, match="unexpected value"):
        verify_keyring_live.verify_isolated_fallback(tmp_path)

    assert mutations == []


def test_isolated_fallback_removes_exact_fake_residue_before_writing(tmp_path, monkeypatch):
    stored = {"value": verify_keyring_live.FALLBACK_VALUE}
    operations = []

    def fake_get(*args, **kwargs):
        operations.append(("get", stored["value"]))
        return stored["value"]

    def fake_delete(*args, **kwargs):
        operations.append(("delete", stored["value"]))
        stored["value"] = None

    def fake_set(env_name, value, **kwargs):
        operations.append(("set", value))
        stored["value"] = value

    def fake_resolve(*args, **kwargs):
        stored["value"] = verify_keyring_live.FALLBACK_VALUE
        return verify_keyring_live.SecretResolution(
            {"OPENAI_API_KEY": verify_keyring_live.FALLBACK_VALUE},
            (verify_keyring_live.FALLBACK_ENV_NAME,),
        )

    monkeypatch.setattr(verify_keyring_live, "get_api_key", fake_get)
    monkeypatch.setattr(verify_keyring_live, "delete_api_key", fake_delete)
    monkeypatch.setattr(verify_keyring_live, "set_api_key", fake_set)
    monkeypatch.setattr(verify_keyring_live, "resolve_api_keys", fake_resolve)

    assert verify_keyring_live.verify_isolated_fallback(tmp_path)
    assert [operation[0] for operation in operations[:5]] == [
        "get",
        "get",
        "delete",
        "get",
        "set",
    ]
    assert operations[0][1] == verify_keyring_live.FALLBACK_VALUE


def test_isolated_fallback_rejects_value_not_migrated_from_temp_env(tmp_path, monkeypatch):
    stored = {"value": None}

    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda *args, **kwargs: stored["value"],
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "set_api_key",
        lambda env_name, value, **kwargs: stored.update(value=value),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "delete_api_key",
        lambda *args, **kwargs: stored.update(value=None),
    )

    def fake_resolve(*args, **kwargs):
        stored["value"] = verify_keyring_live.FALLBACK_VALUE
        return verify_keyring_live.SecretResolution(
            {verify_keyring_live.FALLBACK_ENV_NAME: verify_keyring_live.FALLBACK_VALUE}
        )

    monkeypatch.setattr(verify_keyring_live, "resolve_api_keys", fake_resolve)

    assert not verify_keyring_live.verify_isolated_fallback(tmp_path)


def test_delete_fallback_requires_absent_readback(monkeypatch):
    calls = []
    monkeypatch.setattr(
        verify_keyring_live,
        "delete_api_key",
        lambda *args, **kwargs: calls.append("delete"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda *args, **kwargs: calls.append("get") or verify_keyring_live.FALLBACK_VALUE,
    )

    with pytest.raises(RuntimeError, match="still present"):
        verify_keyring_live._delete_fallback()

    assert calls == ["get", "delete", "get"]


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
        lambda path, *, settings_path: loaded_paths.append(
            (Path(path), Path(settings_path))
        )
        or config,
    )

    def fake_get(env_name, *, service_name, key_names):
        read_names.append((env_name, key_names[env_name]))
        return secrets[env_name]

    monkeypatch.setattr(verify_keyring_live, "get_api_key", fake_get)
    monkeypatch.setattr(
        verify_keyring_live,
        "test_openai_key",
        lambda value: (False, f"request failed url=https://example.invalid/?key={value} body=unsafe"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "test_gemini_key",
        lambda value: (True, f"connected with {value} helper-details"),
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "test_minimax_key",
        lambda value: (True, f"connected with {value} response-body"),
    )
    monkeypatch.setattr(verify_keyring_live, "verify_isolated_fallback", lambda root: True)

    real_env = tmp_path / "real.env"
    verify_keyring_live.run_live_verification(real_env, tmp_path)

    output = capsys.readouterr().out
    assert loaded_paths[0][0] == real_env
    settings_path = loaded_paths[0][1].resolve()
    assert settings_path.is_relative_to(tmp_path.resolve())
    assert settings_path.name == "settings.json"
    assert read_names == [
        ("OPENAI_API_KEY", "openai_api_key"),
        ("GEMINI_API_KEY", "gemini_api_key"),
        ("MINIMAX_API_KEY", "minimax_api_key"),
    ]
    assert all(secret not in output for secret in secrets.values())
    assert "request failed" not in output
    assert "example.invalid" not in output
    assert "helper-details" not in output
    assert "response-body" not in output
    assert "provider OpenAI: FAIL" in output
    assert "provider Gemini: PASS" in output
    assert "provider MiniMax: PASS" in output
    assert "exists=PASS" in output
    assert "matches_resolved=PASS" in output


def test_live_verification_converts_provider_exception_to_fixed_failure_status(
    tmp_path, monkeypatch, capsys
):
    config = SimpleNamespace(
        openai_api_key="openai-secret",
        gemini_api_key="gemini-secret",
        minimax_api_key="",
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "load_config",
        lambda path, *, settings_path: config,
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "get_api_key",
        lambda env_name, **kwargs: {
            "OPENAI_API_KEY": config.openai_api_key,
            "GEMINI_API_KEY": config.gemini_api_key,
            "MINIMAX_API_KEY": None,
        }[env_name],
    )
    monkeypatch.setattr(
        verify_keyring_live,
        "test_openai_key",
        lambda value: (_ for _ in ()).throw(
            RuntimeError(f"unsafe exception url=https://example.invalid/?key={value}")
        ),
    )
    monkeypatch.setattr(verify_keyring_live, "test_gemini_key", lambda value: (True, "OK"))
    monkeypatch.setattr(verify_keyring_live, "verify_isolated_fallback", lambda root: True)

    assert not verify_keyring_live.run_live_verification(tmp_path / "real.env", tmp_path)
    output = capsys.readouterr().out
    assert "provider OpenAI: FAIL" in output
    assert "unsafe exception" not in output
    assert "example.invalid" not in output
    assert "openai-secret" not in output


def test_live_verification_allows_optional_minimax_key_to_be_absent(
    tmp_path, monkeypatch, capsys
):
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
    monkeypatch.setattr(
        verify_keyring_live,
        "load_config",
        lambda path, *, settings_path: config,
    )
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
    output = capsys.readouterr().out
    assert "provider MiniMax" not in output
    assert "SKIP" not in output
