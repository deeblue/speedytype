# macOS Python Preflight and 0.5.3 Release Design

## Goal

Make macOS setup fail early with actionable guidance when the selected Python or an existing virtual environment is older than Python 3.13, then publish the fix as SpeedyType 0.5.3 without changing the immutable 0.5.2 release.

## Observed Failure

The real macOS 0.5.2 setup log shows that `setup_mac.sh` selected the default `python3`, created `.venv`, and reached dependency installation with pip 21.2.4. Installation then failed because `audioop-lts==0.2.2` had no distribution compatible with that Python environment. Since the script uses `set -e`, command-alias installation and every later verification step did not run.

The Windows-only dependency messages in the log are expected marker handling and are not errors. The user-provided `docs/log/mac_log_000.rtf` remains an untracked test record and is not included in the source release.

## Setup Behavior

`scripts/setup_mac.sh` will require Python 3.13 or newer. It will retain the current selection rule: use `$PYTHON` when explicitly supplied, otherwise use `python3`.

Before creating `.venv`, the script will:

1. Verify that the selected executable can be found and launched.
2. Read its Python version.
3. Exit before creating files when the version is below 3.13.

When `.venv/bin/python` already exists, the script will validate that interpreter independently. A stale environment below Python 3.13 will cause setup to stop with its detected version, the `.venv` path, and explicit recovery commands. The script will never delete or overwrite an incompatible environment automatically.

After a compatible environment is available, setup will run:

```sh
"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command
```

Every command remains covered by `set -euo pipefail`, so alias installation cannot be reported as complete after a failed pip operation.

## Error Guidance

The error message will distinguish these cases:

- The selected bootstrap executable does not exist or cannot run.
- The selected bootstrap Python is older than 3.13.
- The existing `.venv` uses Python older than 3.13.

For an incompatible existing environment, the message will tell the user to remove or move `.venv` deliberately, install Python 3.13 through Homebrew if needed, and rerun with:

```sh
PYTHON="$(brew --prefix python@3.13)/bin/python3.13" bash scripts/setup_mac.sh
```

The script will not run Homebrew or delete `.venv` itself.

## Documentation

`MAC_SETUP.md` will state Python 3.13+ as a prerequisite before the normal setup commands. It will document `python3 --version`, `.venv/bin/python --version`, the Homebrew installation command, safe stale-venv recovery, and the explicit `$PYTHON` invocation. The existing zsh, unzip permissions, Keychain, PATH, Gatekeeper, and macOS privacy guidance will remain intact.

## Testing

Tests will verify that the macOS setup script:

- defines and enforces a minimum Python version of 3.13;
- validates both the bootstrap interpreter and an existing venv interpreter;
- does not contain an automatic recursive deletion of `.venv`;
- upgrades pip before installing `requirements.txt`;
- installs the command alias only after dependency installation;
- retains valid Bash syntax.

Documentation tests will verify the Python 3.13 prerequisite and recovery commands. The existing setup, release, CLI version, About dialog, and build tests will remain green.

## Release

After the fix passes the complete suite, update the authoritative version to 0.5.3, update current release documentation and version contracts, build the source archive twice, and require byte-identical SHA-256 output. Extract the real archive and verify the CLI version, package version, macOS script syntax, Windows script parsing, and the new macOS preflight/documentation content.

Commit the verified release on `master`, create an annotated local `v0.5.3` tag only after post-commit verification, and do not push without separate user authorization. Existing `v0.5.2` and its artifacts remain unchanged.
