"""Provision the bundled Groq STT key into the local OS credential store."""

from __future__ import annotations

import argparse
from collections.abc import Mapping
import os
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from speedytype.secrets_store import set_api_key


ENV_NAME = "GROQ_API_KEY"


def resolve_groq_key(key_file: str | Path | None, environment: Mapping[str, str] | None = None) -> str:
    if environment is None:
        environment = os.environ
    if key_file is not None:
        value = Path(key_file).read_text(encoding="utf-8").strip()
    else:
        value = environment.get(ENV_NAME, "").strip()
    if not value:
        raise ValueError("GROQ_API_KEY is empty; provide it via environment or --key-file.")
    return value


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Store the bundled Groq API key in SpeedyType's keyring.")
    parser.add_argument(
        "--key-file",
        type=Path,
        help="Read the Groq API key from this local provisioning file instead of GROQ_API_KEY.",
    )
    args = parser.parse_args(argv)
    try:
        key = resolve_groq_key(args.key_file)
        set_api_key(ENV_NAME, key)
    except Exception as exc:
        print(f"Groq key provisioning failed: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 1
    print("Groq key provisioned into SpeedyType keyring.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
