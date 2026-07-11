from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import json


DEFAULT_VOCAB_TERMS = ["BIOS", "Firmware", "NPI", "QA", "API", "TPE 團隊", "BJ 團隊", "USB", "Thunderbolt"]
DEFAULT_MAX_RECORD_SECONDS = 60.0
DEFAULT_HOTKEY_COMBO = ["f9"]

MIN_MAX_RECORD_SECONDS = 60.0
MAX_MAX_RECORD_SECONDS = 540.0

SETTINGS_FILE_NAME = "settings.json"

MODIFIER_KEYS = {"ctrl", "alt", "shift", "windows", "win"}


def _is_function_key(key: str) -> bool:
    key = key.lower()
    if not key.startswith("f"):
        return False
    rest = key[1:]
    return rest.isdigit() and 1 <= int(rest) <= 24


def hotkey_has_modifier_or_is_function_key(combo: list[str]) -> bool:
    """A saved hotkey must either include a modifier key, or be a single
    dedicated function key (F1-F24), so it can never collide with ordinary
    typing (e.g. a lone spacebar) while still allowing the existing safe
    single-key default (F9) to remain valid without forcing a modifier.
    """
    if not combo:
        return False
    if len(combo) == 1 and _is_function_key(combo[0]):
        return True
    return any(key.lower() in MODIFIER_KEYS for key in combo)


@dataclass(frozen=True)
class AppSettings:
    max_record_seconds: float = DEFAULT_MAX_RECORD_SECONDS
    hotkey_combo: list[str] = field(default_factory=lambda: list(DEFAULT_HOTKEY_COMBO))
    vocab_terms: list[str] = field(default_factory=lambda: list(DEFAULT_VOCAB_TERMS))
    # Empty string means "system default input device". Stored by name, not
    # index, since device indices can shift across reboots/replugs; the name
    # is re-resolved to a live index at startup (see config.load_config).
    mic_device_name: str = ""

    @property
    def hotkey_string(self) -> str:
        """Canonical `keyboard`-library hotkey string, e.g. 'ctrl+alt+space'."""
        return "+".join(self.hotkey_combo)

    @property
    def vocab_bias_string(self) -> str:
        return ", ".join(self.vocab_terms)

    def to_dict(self) -> dict:
        return {
            "max_record_seconds": self.max_record_seconds,
            "hotkey_combo": list(self.hotkey_combo),
            "vocab_terms": list(self.vocab_terms),
            "mic_device_name": self.mic_device_name,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "AppSettings":
        return cls(
            max_record_seconds=float(data.get("max_record_seconds", DEFAULT_MAX_RECORD_SECONDS)),
            hotkey_combo=list(data.get("hotkey_combo", DEFAULT_HOTKEY_COMBO)) or list(DEFAULT_HOTKEY_COMBO),
            vocab_terms=list(data.get("vocab_terms", DEFAULT_VOCAB_TERMS)) or list(DEFAULT_VOCAB_TERMS),
            mic_device_name=str(data.get("mic_device_name", "") or ""),
        )

    @classmethod
    def default(cls) -> "AppSettings":
        return cls()


def load_settings(path: str | Path = SETTINGS_FILE_NAME) -> AppSettings:
    """Load settings.json, auto-creating it with defaults if missing, and
    falling back to in-memory defaults (without touching the file) if its
    content is not valid JSON/schema, so a manually-broken file can never
    crash the app.
    """
    settings_path = Path(path)
    if not settings_path.exists():
        defaults = AppSettings.default()
        save_settings(settings_path, defaults)
        return defaults

    try:
        raw = settings_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            raise ValueError(f"settings.json root must be an object, got {type(data).__name__}")
        return AppSettings.from_dict(data)
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        print(
            f"Warning: could not read {settings_path} ({exc}); using default settings for this run. "
            f"The file was left untouched so you can inspect/fix it manually.",
            flush=True,
        )
        return AppSettings.default()


def save_settings(path: str | Path, settings: AppSettings) -> None:
    settings_path = Path(path)
    settings_path.write_text(
        json.dumps(settings.to_dict(), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def export_vocab(path: str | Path, terms: list[str]) -> None:
    Path(path).write_text(
        json.dumps({"vocab_terms": list(terms)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def import_vocab(path: str | Path) -> list[str]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("vocab_terms"), list):
        raise ValueError("Vocab file must be a JSON object with a 'vocab_terms' list.")
    return [str(term) for term in data["vocab_terms"]]
