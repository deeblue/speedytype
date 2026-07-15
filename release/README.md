# SpeedyType Source Release

SpeedyType is a local Windows/macOS voice-input daemon. It records from a
configurable hotkey, transcribes speech, optionally polishes text, and pastes
the result into the active application.

## Prerequisites

- Python 3.13 (64-bit recommended)
- A working microphone
- Windows 10/11 or a supported macOS version
- OpenAI plus the selected LLM provider credentials

Extract the complete release ZIP before running setup. Do not run setup from
inside the ZIP viewer.

## Automatic setup

Open a terminal in the extracted release directory.

Windows PowerShell:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

macOS:

```sh
./scripts/setup_mac.sh
```

Both scripts create or reuse `.venv`, run `pip install -r requirements.txt`,
and install the short `speedytype` command. Open a new terminal afterward.

## Manual setup

Windows PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m speedytype install-command
```

macOS:

```sh
python3 -m venv .venv
./.venv/bin/python -m pip install --upgrade pip
./.venv/bin/python -m pip install -r requirements.txt
./.venv/bin/python -m speedytype install-command
```

Open a new terminal after `install-command` so the updated PATH is available.

## Credentials and first start

Open Settings before starting the daemon:

```text
speedytype settings
```

API key fields stay masked but accept typing and native paste immediately; the
**Show** button is only needed when you want to inspect the entered value.

Enter the OpenAI key and the key for the selected LLM provider, test the
connections, and save. Keys are stored by Keyring in Windows Credential Manager
or macOS Keychain. Do not put new keys in `.env`; file keys exist only for
legacy fallback and migration. Use `.env.example` as a non-secret configuration
reference.

After saving keys:

```text
speedytype diagnose-config
speedytype daemon
```

The tray menu can reopen Settings, restart the daemon, or exit it.

## Daily commands

```text
speedytype settings
speedytype --version
speedytype diagnose-config
speedytype daemon
speedytype daemon-stop
speedytype guided-recording --script real_voice_script.md
speedytype --env other.env daemon
```

The `--env` option must appear before the action. All remaining action
arguments are forwarded unchanged by the installed wrapper.

## Updating

Replace the extracted release files with the newer release and rerun the
platform setup script. The venv and command wrapper are refreshed safely;
Keyring credentials are not copied, deleted, or changed by setup.

## Troubleshooting

- Windows: open a new terminal if `speedytype` is not found. Rerun setup to
  refresh the user PATH entry, then try `speedytype diagnose-config`.
- macOS: if requested, add
  `export PATH="$HOME/.local/bin:$PATH"` to `~/.zshrc` or
  `~/.bash_profile`, then open a new terminal.
- macOS: grant Accessibility and Input Monitoring permissions to the selected
  Python executable. See `MAC_SETUP.md` for the real-device checklist.
- Configuration errors: run `speedytype settings`, save the required keys, and
  then rerun `speedytype diagnose-config`.
- Daemon state: use `speedytype daemon-stop` before manually starting another
  daemon instance.

## Verify the archive

Compare the downloaded ZIP SHA-256 with `SHA256SUMS.txt`.

Windows:

```powershell
Get-FileHash SpeedyType-0.5.1-source.zip -Algorithm SHA256
```

macOS:

```sh
shasum -a 256 SpeedyType-0.5.1-source.zip
```

Real macOS runtime verification remains required before describing Mac command
installation as fully verified.
