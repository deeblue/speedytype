from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.config import AppConfig, load_config
from speedytype.env_writer import test_gemini_key, test_minimax_key, test_openai_key
from speedytype.paths import default_env_path
from speedytype.secrets_store import (
    SECRET_KEY_NAMES,
    SecretStoreError,
    delete_api_key,
    get_api_key,
    resolve_api_keys,
    set_api_key,
)


FALLBACK_USERNAME = "fallback_test_api_key"
FALLBACK_ENV_NAME = "OPENAI_API_KEY"
FALLBACK_VALUE = "speedytype-fake-not-a-real-key"
FALLBACK_KEY_NAMES = {FALLBACK_ENV_NAME: FALLBACK_USERNAME}


def _delete_fallback_credential() -> None:
    username = FALLBACK_KEY_NAMES[FALLBACK_ENV_NAME]
    assert username == "fallback_test_api_key"
    delete_api_key(FALLBACK_ENV_NAME, key_names=FALLBACK_KEY_NAMES)


def run_isolated_fallback_check(temp_dir: str | Path) -> bool:
    temp_root = Path(temp_dir).resolve()
    temp_root.mkdir(parents=True, exist_ok=True)
    env_path = temp_root / "keyring_fallback_test.env"
    env_path.write_text(f"{FALLBACK_ENV_NAME}={FALLBACK_VALUE}\n", encoding="utf-8")

    try:
        set_api_key(
            FALLBACK_ENV_NAME,
            FALLBACK_VALUE,
            key_names=FALLBACK_KEY_NAMES,
        )
        if get_api_key(FALLBACK_ENV_NAME, key_names=FALLBACK_KEY_NAMES) != FALLBACK_VALUE:
            return False

        _delete_fallback_credential()
        result = resolve_api_keys(
            env_path,
            {FALLBACK_ENV_NAME: FALLBACK_VALUE},
            environment={},
            key_names=FALLBACK_KEY_NAMES,
        )
        return (
            result.values.get(FALLBACK_ENV_NAME) == FALLBACK_VALUE
            and get_api_key(FALLBACK_ENV_NAME, key_names=FALLBACK_KEY_NAMES) == FALLBACK_VALUE
        )
    finally:
        _delete_fallback_credential()


def _config_secret(config: AppConfig, env_name: str) -> str:
    return {
        "OPENAI_API_KEY": config.openai_api_key,
        "GEMINI_API_KEY": config.gemini_api_key,
        "MINIMAX_API_KEY": config.minimax_api_key,
    }[env_name]


def _redact(message: str, secret: str) -> str:
    return message.replace(secret, "[REDACTED]") if secret else message


def verify_production_credentials(env_path: Path) -> tuple[bool, AppConfig | None]:
    try:
        config = load_config(env_path)
    except Exception as exc:
        print(f"PRODUCTION_MIGRATION NOT_VERIFIED ({type(exc).__name__})")
        return False, None

    all_match = True
    for env_name in SECRET_KEY_NAMES:
        expected = _config_secret(config, env_name)
        try:
            stored = get_api_key(env_name)
        except SecretStoreError as exc:
            print(f"{env_name}: NOT_VERIFIED ({exc})")
            all_match = False
            continue
        exists = bool(stored)
        matches = stored == expected if expected else not exists
        print(f"{env_name}: exists={exists} matches_resolved_config={matches}")
        all_match = all_match and matches
    return all_match, config


def verify_provider_connections(config: AppConfig) -> bool:
    checks = (
        ("OpenAI", config.openai_api_key, test_openai_key),
        ("Gemini", config.gemini_api_key, test_gemini_key),
        ("MiniMax", config.minimax_api_key, test_minimax_key),
    )
    all_ok = True
    for provider, secret, check in checks:
        if not secret and provider == "MiniMax":
            print("MiniMax connection: SKIPPED (optional key absent)")
            continue
        ok, message = check(secret)
        print(f"{provider} connection: {'PASS' if ok else 'FAIL'} - {_redact(message, secret)}")
        all_ok = all_ok and ok
    return all_ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify SpeedyType keyring migration without printing secrets.")
    parser.add_argument("--env", type=Path, default=default_env_path())
    args = parser.parse_args()

    credentials_ok, config = verify_production_credentials(args.env.resolve())
    connections_ok = verify_provider_connections(config) if config is not None else False

    try:
        with tempfile.TemporaryDirectory(prefix="speedytype_keyring_verify_") as temp_dir:
            fallback_ok = run_isolated_fallback_check(temp_dir)
    except Exception as exc:
        print(f"ISOLATED_FALLBACK NOT_VERIFIED ({type(exc).__name__})")
        fallback_ok = False
    else:
        print(f"ISOLATED_FALLBACK: {'PASS' if fallback_ok else 'FAIL'}")

    return 0 if credentials_ok and connections_ok and fallback_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
