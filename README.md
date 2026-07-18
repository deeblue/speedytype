# SpeedyType Development Tree

This repository is the SpeedyType development tree. End-user installation and
operation instructions, current status, architecture, decisions, limitations,
and historical evidence are organized in the
[documentation hub](docs/README.md).

## Development Setup

SpeedyType requires Python 3.13 or newer. Create a virtual environment and
install the pinned dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

On macOS/Linux, use `python3 -m venv .venv` and `.venv/bin/python` for the same
commands.

## Verification

Run the automated tests and compile the Python sources:

```text
python -m pytest -q
python -m compileall -q speedytype scripts
```

The `tests/` tree includes unit, platform-contract, recovery, release, and
documentation checks. Benchmark and long-recording experiment tooling is kept
out of the user release.

## Build a Clean Release

```text
python scripts/build_release.py
```

The deterministic builder writes the extracted source release to
`dist/SpeedyType-<version>/`, the archive to
`dist/SpeedyType-<version>-source.zip`, and its checksum to
`dist/SHA256SUMS.txt`.

## Runtime Input Assets

`real_voice_script.md` and `real_voice_script_round2.md` remain at repository
root because they are guided-recording/benchmark input assets, not
documentation sources.
