from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import os
import shlex

from speedytype.audio import find_input_device_index_by_name
from speedytype.paths import default_env_path, default_latency_log_path
from speedytype.secrets_store import SecretResolution, resolve_api_keys
from speedytype.settings import SETTINGS_FILE_NAME, load_settings


DEFAULT_VOCAB_BIAS = "BIOS, Firmware, NPI, QA, API, PD, USB, Thunderbolt, TPE 團隊, BJ 團隊"
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash"


class ConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class AppConfig:
    openai_api_key: str
    gemini_api_key: str
    minimax_api_key: str = ""
    mic_device: str = ""
    mic_device_warning: str = ""
    whisper_vocab_bias: str = DEFAULT_VOCAB_BIAS
    hotkey: str = "f9"
    gemini_model: str = DEFAULT_GEMINI_MODEL
    llm_provider: str = "gemini"
    llm_model: str = DEFAULT_GEMINI_MODEL
    llm_reasoning_effort: str = ""
    llm_thinking_level: str = ""
    llm_thinking_type: str = ""
    llm_disambiguation_hints: str = "on"
    max_record_seconds: float = 60.0
    latency_log_path: Path = field(default_factory=default_latency_log_path)
    clipboard_restore_delay_seconds: float = 0.3
    hybrid_transcription_enabled: bool = False
    hybrid_threshold_seconds: float = 90.0

    @property
    def use_disambiguation_hints(self) -> bool:
        return self.llm_disambiguation_hints.strip().lower() not in {"0", "false", "no", "off"}


def _parse_env_file(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if value:
            try:
                parsed = shlex.split(value, posix=False)
                if len(parsed) == 1:
                    value = parsed[0].strip('"').strip("'")
            except ValueError:
                value = value.strip('"').strip("'")
        values[key] = value
    return values


def resolve_mic_device_setting(device_name: str) -> tuple[str, str]:
    """Resolve a device name saved in settings.json against currently
    available input devices.

    Returns (mic_device_value_for_AppConfig, warning_message). An empty
    device_name means "system default" and always resolves cleanly. A
    non-empty name that can no longer be found (unplugged, replaced, etc.)
    falls back to the system default and returns a non-empty warning message
    instead of raising, so a missing device can never crash startup.
    """
    if not device_name:
        return "", ""
    if find_input_device_index_by_name(device_name) is not None:
        return device_name, ""
    return "", (
        f"先前選定的錄音裝置「{device_name}」目前找不到（可能已拔除或更換），"
        "已自動改用系統預設裝置。請至設定頁面重新選擇。"
    )


def load_config(
    path: str | Path | None = None,
    settings_path: str | Path | None = None,
    *,
    require_api_keys: bool = True,
) -> AppConfig:
    env_path = Path(path) if path is not None else default_env_path()
    file_values = _parse_env_file(env_path)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name, default)).strip()

    resolution: SecretResolution = resolve_api_keys(env_path, file_values, os.environ)
    for provider_name in resolution.migrated:
        print(f"Migrated {provider_name} to keyring.")
    for warning in resolution.warnings:
        print(f"Warning: {warning}")

    openai_api_key = resolution.values.get("OPENAI_API_KEY", "").strip()
    gemini_api_key = resolution.values.get("GEMINI_API_KEY", "").strip()
    missing = [name for name, value in (("OPENAI_API_KEY", openai_api_key), ("GEMINI_API_KEY", gemini_api_key)) if not value]
    if missing and require_api_keys:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + ". 請從 SpeedyType 設定頁面新增金鑰，或在 keyring 不可用時於 .env 提供備援值："
            + f"{env_path.resolve()}."
        )

    # Behavior settings (max recording length, hotkey, vocabulary bias, mic
    # device) now live in settings.json, editable from the Settings dialog,
    # instead of .env. Any MAX_RECORD_SECONDS/HOTKEY/WHISPER_VOCAB_BIAS/
    # MIC_DEVICE lines still present in .env are no longer read; settings.json
    # is auto-created with defaults if missing.
    settings = load_settings(settings_path)
    mic_device_value, mic_device_warning = resolve_mic_device_setting(settings.mic_device_name)

    return AppConfig(
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        minimax_api_key=resolution.values.get("MINIMAX_API_KEY", "").strip(),
        mic_device=mic_device_value,
        mic_device_warning=mic_device_warning,
        whisper_vocab_bias=settings.vocab_bias_string,
        hotkey=settings.hotkey_string,
        gemini_model=get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL,
        llm_provider=get("LLM_PROVIDER", "gemini") or "gemini",
        llm_model=get("LLM_MODEL", get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL),
        llm_reasoning_effort=get("LLM_REASONING_EFFORT"),
        llm_thinking_level=get("LLM_THINKING_LEVEL"),
        llm_thinking_type=get("LLM_THINKING_TYPE"),
        llm_disambiguation_hints=get("LLM_DISAMBIGUATION_HINTS", "on") or "on",
        max_record_seconds=settings.max_record_seconds,
        latency_log_path=Path(get("LATENCY_LOG_PATH", str(default_latency_log_path())) or default_latency_log_path()),
        clipboard_restore_delay_seconds=float(get("CLIPBOARD_RESTORE_DELAY_SECONDS", "0.3") or "0.3"),
        hybrid_transcription_enabled=get("HYBRID_TRANSCRIPTION_ENABLED", "false").lower() in {"1", "true", "yes", "on"},
        hybrid_threshold_seconds=float(get("HYBRID_THRESHOLD_SECONDS", "90") or "90"),
    )
