from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import shlex


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
    whisper_vocab_bias: str = DEFAULT_VOCAB_BIAS
    hotkey: str = "f9"
    gemini_model: str = DEFAULT_GEMINI_MODEL
    llm_provider: str = "gemini"
    llm_model: str = DEFAULT_GEMINI_MODEL
    llm_reasoning_effort: str = ""
    llm_thinking_level: str = ""
    llm_thinking_type: str = ""
    llm_disambiguation_hints: str = "on"
    max_record_seconds: float = 30.0
    latency_log_path: Path = Path("speedytype_latency_log.csv")

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


def load_config(path: str | Path = ".env") -> AppConfig:
    env_path = Path(path)
    file_values = _parse_env_file(env_path)

    def get(name: str, default: str = "") -> str:
        return os.environ.get(name, file_values.get(name, default)).strip()

    openai_api_key = get("OPENAI_API_KEY")
    gemini_api_key = get("GEMINI_API_KEY")
    missing = [name for name, value in (("OPENAI_API_KEY", openai_api_key), ("GEMINI_API_KEY", gemini_api_key)) if not value]
    if missing:
        raise ConfigError(
            "Missing required configuration: "
            + ", ".join(missing)
            + f". Copy .env.example to .env and fill the keys in {env_path.resolve()}."
        )

    return AppConfig(
        openai_api_key=openai_api_key,
        gemini_api_key=gemini_api_key,
        minimax_api_key=get("MINIMAX_API_KEY"),
        mic_device=get("MIC_DEVICE"),
        whisper_vocab_bias=get("WHISPER_VOCAB_BIAS", DEFAULT_VOCAB_BIAS) or DEFAULT_VOCAB_BIAS,
        hotkey=get("HOTKEY", "f9") or "f9",
        gemini_model=get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL,
        llm_provider=get("LLM_PROVIDER", "gemini") or "gemini",
        llm_model=get("LLM_MODEL", get("GEMINI_MODEL", DEFAULT_GEMINI_MODEL) or DEFAULT_GEMINI_MODEL),
        llm_reasoning_effort=get("LLM_REASONING_EFFORT"),
        llm_thinking_level=get("LLM_THINKING_LEVEL"),
        llm_thinking_type=get("LLM_THINKING_TYPE"),
        llm_disambiguation_hints=get("LLM_DISAMBIGUATION_HINTS", "on") or "on",
        max_record_seconds=float(get("MAX_RECORD_SECONDS", "30") or "30"),
        latency_log_path=Path(get("LATENCY_LOG_PATH", "speedytype_latency_log.csv") or "speedytype_latency_log.csv"),
    )
