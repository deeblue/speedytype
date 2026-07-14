# Keyring Secrets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the OS credential store the primary storage for all three API keys, safely migrate verified `.env` values, and preserve every existing Settings key-field behavior.

**Architecture:** `speedytype/secrets_store.py` owns all `keyring` calls and line-removal migration. `config.py` asks it to resolve keys before constructing `AppConfig`; `settings_dialog.py` saves changed secrets through the same API. Backend failures produce non-secret warnings and use environment/`.env` fallback without deleting source values.

**Tech Stack:** Python 3.13, keyring, pytest, PyQt6, Windows Credential Manager/macOS Keychain.

## Global Constraints

- Keyring service name is exactly `SpeedyType`.
- Production usernames are exactly `openai_api_key`, `gemini_api_key`, and `minimax_api_key`.
- Never log, assert, or display a complete real secret.
- Never remove an `.env` secret before a successful set-and-read-back equality check.
- Live fallback verification may mutate only the extra fake username `fallback_test_api_key` and a temporary `.env`; production usernames are read-only during that test.
- OpenAI and Gemini remain required; MiniMax remains optional.

---

## File Structure

- `speedytype/secrets_store.py`: keyring adapter, resolution result, verified write/delete, `.env` secret-line scrubbing.
- `speedytype/config.py`: calls secret resolution and improves missing-key guidance.
- `speedytype/settings_dialog.py`: keeps field UX but saves key changes to keyring.
- `requirements.txt`: pins `keyring`.
- `tests/test_secrets_store.py`: unit tests with injected fake keyring functions.
- `tests/conftest.py`: process-wide in-memory keyring fixture preventing pytest from touching real OS credentials.
- `tests/test_config.py`: keyring priority/fallback/error integration tests.
- `tests/test_settings_dialog.py`: Qt storage, masking, test button, deletion, failure, and cancel tests.
- `scripts/verify_keyring_live.py`: guarded Windows live verification using real production reads and an isolated fake fallback credential.
- `KNOWN_LIMITATIONS.md`, `POC_REPORT.md`: Part A documentation and evidence.

### Task 1: Keyring adapter and safe `.env` migration

**Files:**
- Create: `speedytype/secrets_store.py`
- Create: `tests/test_secrets_store.py`
- Create: `tests/conftest.py`
- Modify: `requirements.txt`

**Interfaces:**
- Produces: `SecretStoreError`, `SecretResolution`, `get_api_key()`, `set_api_key()`, `delete_api_key()`, `resolve_api_keys()`.
- `resolve_api_keys(env_path, file_values, environment=None, service_name=SERVICE_NAME, key_names=SECRET_KEY_NAMES) -> SecretResolution`.

- [ ] **Step 1: Add the dependency and failing adapter tests**

Add `keyring==25.7.0` to `requirements.txt` (the current PyPI release verified on 2026-07-14). Add this autouse fixture in `tests/conftest.py` so no pytest path can touch real OS credentials; individual adapter tests may override the same module callables:

```python
import pytest


@pytest.fixture(autouse=True)
def isolated_keyring(monkeypatch):
    from speedytype import secrets_store

    values = {}
    monkeypatch.setattr(secrets_store, "_get_password", lambda service, user: values.get((service, user)))
    monkeypatch.setattr(secrets_store, "_set_password", lambda service, user, value: values.__setitem__((service, user), value))
    monkeypatch.setattr(secrets_store, "_delete_password", lambda service, user: values.pop((service, user), None))
    for env_name in secrets_store.SECRET_KEY_NAMES:
        monkeypatch.delenv(env_name, raising=False)
    yield values
```

Create tests that inject module-level `_get_password`, `_set_password`, and `_delete_password` callables:

```python
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
```

- [ ] **Step 2: Run the tests and verify RED**

Run: `python -m pytest tests/test_secrets_store.py -v`

Expected: collection fails with `ImportError: cannot import name 'secrets_store'`.

- [ ] **Step 3: Implement the minimal adapter and resolver**

Implement constants, dataclass, wrapper functions, and a `_remove_env_keys()` helper. Convert every backend exception into `SecretStoreError`; `resolve_api_keys()` catches it per key, retains fallback, and scrubs only successfully migrated file-sourced keys. Environment values override file fallback but are not migrated.

```python
SERVICE_NAME = "SpeedyType"
SECRET_KEY_NAMES = {
    "OPENAI_API_KEY": "openai_api_key",
    "GEMINI_API_KEY": "gemini_api_key",
    "MINIMAX_API_KEY": "minimax_api_key",
}

@dataclass(frozen=True)
class SecretResolution:
    values: dict[str, str]
    migrated: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()

def set_api_key(env_name: str, value: str, *, service_name: str = SERVICE_NAME,
                key_names: Mapping[str, str] = SECRET_KEY_NAMES) -> None:
    username = key_names[env_name]
    try:
        _set_password(service_name, username, value)
        if _get_password(service_name, username) != value:
            raise SecretStoreError(f"Credential verification failed for {env_name}")
    except SecretStoreError:
        raise
    except Exception as exc:
        raise SecretStoreError(f"Credential store failed for {env_name}: {exc}") from exc
```

Use `splitlines(keepends=True)` when removing active `KEY=...` lines so comments, blank lines, newline style, and all unrelated bytes remain unchanged.

- [ ] **Step 4: Run adapter tests and the existing env-writer tests**

Run: `python -m pytest tests/test_secrets_store.py tests/test_env_writer.py -v`

Expected: all tests pass; existing non-secret `.env` writer behavior remains intact.

- [ ] **Step 5: Commit**

```text
git add requirements.txt speedytype/secrets_store.py tests/conftest.py tests/test_secrets_store.py
git commit -m "feat: add verified keyring secret storage"
```

### Task 2: Config keyring priority and startup migration

**Files:**
- Modify: `speedytype/config.py:91-136`
- Modify: `tests/test_config.py`

**Interfaces:**
- Consumes: `resolve_api_keys()` from Task 1.
- Produces: `load_config()` with unchanged signature and keyring-first semantics.

- [ ] **Step 1: Write failing config tests**

Add tests that monkeypatch `speedytype.config.resolve_api_keys` with explicit `SecretResolution` values:

```python
def test_load_config_uses_resolved_keyring_values(tmp_path, monkeypatch):
    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=file-openai\nGEMINI_API_KEY=file-gemini\n", encoding="utf-8")
    monkeypatch.setattr(
        "speedytype.config.resolve_api_keys",
        lambda *a, **k: SecretResolution({
            "OPENAI_API_KEY": "ring-openai",
            "GEMINI_API_KEY": "ring-gemini",
            "MINIMAX_API_KEY": "ring-minimax",
        }),
    )
    config = load_config(env_file, settings_path=tmp_path / "settings.json")
    assert config.openai_api_key == "ring-openai"
    assert config.gemini_api_key == "ring-gemini"


def test_load_config_missing_message_mentions_settings_and_env(tmp_path, monkeypatch):
    monkeypatch.setattr("speedytype.config.resolve_api_keys", lambda *a, **k: SecretResolution({}))
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path / ".env", settings_path=tmp_path / "settings.json")
    assert "設定頁面" in str(exc.value)
    assert ".env" in str(exc.value)
```

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_config.py -v`

Expected: tests fail because `load_config()` still reads keys through its generic `get()` helper.

- [ ] **Step 3: Integrate resolution without changing non-secret precedence**

Import `SecretResolution, resolve_api_keys`, call `resolve_api_keys(env_path, file_values, os.environ)`, print only migration provider names and warnings, then build key fields from `resolution.values`. Keep `get()` unchanged for models and tuning settings.

Missing-key copy must be:

```python
"Missing required configuration: OPENAI_API_KEY, GEMINI_API_KEY. "
"請從 SpeedyType 設定頁面新增金鑰，或在 keyring 不可用時於 .env 提供備援值：<resolved path>."
```

- [ ] **Step 4: Run config and secrets tests**

Run: `python -m pytest tests/test_config.py tests/test_secrets_store.py -v`

Expected: all pass, including keyring-empty `.env` fallback and missing-both error.

- [ ] **Step 5: Commit**

```text
git add speedytype/config.py tests/test_config.py
git commit -m "feat: migrate config secrets to keyring"
```

### Task 3: Settings keyring save/delete while preserving key-field UX

**Files:**
- Modify: `speedytype/settings_dialog.py:24-455`
- Modify: `tests/test_settings_dialog.py:108-177`

**Interfaces:**
- Consumes: `set_api_key(env_name, value)` and `delete_api_key(env_name)`.
- Produces: unchanged `MaskedKeyField`; Settings `_save()` reports per-provider success/failure and never writes secret lines.

- [ ] **Step 1: Replace the old `.env` save test with failing keyring tests**

Monkeypatch keyring functions and assert `.env` is byte-for-byte unchanged:

```python
def test_save_writes_only_changed_secret_to_keyring(qapp, tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.json"
    env_path = tmp_path / ".env"
    original_env = "GEMINI_API_KEY=legacy-fallback\n# keep\n"
    env_path.write_text(original_env, encoding="utf-8")
    save_settings(settings_path, AppSettings())
    writes = []
    monkeypatch.setattr("speedytype.settings_dialog.set_api_key", lambda name, value: writes.append((name, value)))
    monkeypatch.setattr("speedytype.settings_dialog.delete_api_key", lambda name: None)
    dialog = SettingsDialog(make_config(), env_path, settings_path)
    dialog.gemini_field.toggle_button.click()
    dialog.gemini_field.line_edit.setText("gem-new-fake")
    dialog.gemini_field.toggle_button.click()
    dialog._save()
    assert writes == [("GEMINI_API_KEY", "gem-new-fake")]
    assert env_path.read_text(encoding="utf-8") == original_env


def test_save_empty_changed_secret_deletes_keyring_entry(qapp, tmp_path, monkeypatch):
    deleted = []
    monkeypatch.setattr("speedytype.settings_dialog.set_api_key", lambda *a: None)
    monkeypatch.setattr("speedytype.settings_dialog.delete_api_key", lambda name: deleted.append(name))
    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")
    dialog.minimax_field.toggle_button.click()
    dialog.minimax_field.line_edit.clear()
    dialog._save()
    assert deleted == ["MINIMAX_API_KEY"]
```

Retain and rerun the current `test_masked_key_field_reveal_toggle_and_edit`; add a test that clicks `test_button` with a fake test function and asserts the currently edited value was passed.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_settings_dialog.py -v`

Expected: keyring tests fail because `_save()` calls `update_env_key()`.

- [ ] **Step 3: Replace secret persistence and security copy**

Remove the `update_env_key` import, import `SecretStoreError, delete_api_key, set_api_key`, and replace the key loop. Track `self._saved_key_values` initialized from config so repeated saves compare against the last successful save. Use this exact help text:

```text
金鑰主要儲存於系統保密管理機制（Windows Credential Manager / macOS Keychain）；.env 僅作為 keyring 不可用時的相容備援。
```

Catch each `SecretStoreError` independently, add `金鑰儲存失敗（ENV_NAME）：<error>` to status, and update `_saved_key_values` only after success.

- [ ] **Step 4: Run Settings and config regression tests**

Run: `python -m pytest tests/test_settings_dialog.py tests/test_config.py tests/test_env_writer.py -v`

Expected: masking, reveal/hide, current-value connection test, cancel-writes-nothing, and keyring save/delete all pass.

- [ ] **Step 5: Commit**

```text
git add speedytype/settings_dialog.py tests/test_settings_dialog.py
git commit -m "feat: save settings secrets through keyring"
```

### Task 4: Guarded live verification and Part A documentation

**Files:**
- Create: `scripts/verify_keyring_live.py`
- Modify: `KNOWN_LIMITATIONS.md:30-35,72-77`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Consumes: production `get_api_key()` and injected `resolve_api_keys()` mapping.
- Produces: a live verifier that never prints secret values and never mutates production usernames in its fallback test.

- [ ] **Step 1: Write the verifier safety test first**

Create `tests/test_keyring_live_script.py` that monkeypatches the script's store calls, executes its isolated fallback function, and asserts every mutated username equals `fallback_test_api_key` and every env path is under `tmp_path`.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_keyring_live_script.py -v`

Expected: import fails because `scripts.verify_keyring_live` does not exist.

- [ ] **Step 3: Implement the guarded verifier**

The script must:

1. call `load_config(real_env_path)` to trigger real migration;
2. report only whether each production username exists and matches the resolved in-memory value;
3. call the existing `test_openai_key`, `test_gemini_key`, and optional `test_minimax_key`, printing status/message but never keys;
4. create `fallback_test_api_key` with `speedytype-fake-not-a-real-key`, verify it, delete only that username, resolve a temporary `.env` through `key_names={"OPENAI_API_KEY": "fallback_test_api_key"}`, and confirm the fake fallback;
5. use `finally` to delete only `fallback_test_api_key`.

Before any delete call, assert `username == "fallback_test_api_key"`; do not accept a username argument from CLI.

- [ ] **Step 4: Run automated safety and Part A tests**

Run: `python -m pytest tests/test_keyring_live_script.py tests/test_secrets_store.py tests/test_config.py tests/test_settings_dialog.py -v`

Expected: all pass.

- [ ] **Step 5: Run Windows live verification and record exact evidence**

Run: `python scripts/verify_keyring_live.py`

Expected: migration/readback and provider connection status are printed without secret values; isolated fallback reports PASS. Independently inspect Windows Credential Manager for `SpeedyType` entries if the UI exposes them.

Then create a temporary non-secret env file containing only model/tuning settings plus `LATENCY_LOG_PATH=<temporary csv>` and run one real daemon cycle through `python scripts/test_daemon_smoke.py --env <temporary env> --runs 1`. This makes the daemon resolve real keys from keyring and execute STT/LLM while keeping the development call out of the production latency log. If a daemon is already running, do not stop or replace it silently; record this live cycle as `NOT_VERIFIED` unless the user authorizes the temporary restart. Record all other failures as `NOT_VERIFIED` with their actual reason.

- [ ] **Step 6: Update documentation**

Change limitation 4 to OS credential storage primary with verified plaintext scrubbing and `.env` compatibility fallback. Change limitation 10 to resolved keyring-backed Settings behavior. Append a Part A section to `POC_REPORT.md` with automated test counts and exact live results.

- [ ] **Step 7: Run Part A verification and commit**

Run: `python -m pytest -q`

Expected: zero failures. Then:

```text
git add scripts/verify_keyring_live.py tests/test_keyring_live_script.py KNOWN_LIMITATIONS.md POC_REPORT.md
git commit -m "test: verify keyring migration and fallback safety"
```
