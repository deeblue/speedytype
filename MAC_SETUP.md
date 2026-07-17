# SpeedyType macOS Setup

macOS Terminal uses zsh by default. These instructions assume the default zsh
environment and a source release extracted into a local, user-owned directory,
such as `~/Applications/SpeedyType`.

## Python prerequisite

SpeedyType requires Python 3.13 or newer. Check the default Python before
running setup:

```sh
python3 --version
```

If it is older than 3.13, install a compatible Homebrew Python and select it
explicitly when running setup:

```sh
brew install python@3.13
PYTHON="$(brew --prefix python@3.13)/bin/python3.13" bash scripts/setup_mac.sh
```

Setup also validates an existing virtual environment without deleting or
replacing it. If setup reports that `.venv` is incompatible, inspect its
version and move it aside before recreating it:

```sh
.venv/bin/python --version
mv .venv .venv.backup
PYTHON="$(brew --prefix python@3.13)/bin/python3.13" bash scripts/setup_mac.sh
```

The `mv` command preserves the old environment for deliberate inspection or
removal. When setup is rerun, it upgrades pip before installing requirements.

## After extracting the release

Some ZIP extractors do not preserve Unix executable permissions. From the
extracted SpeedyType directory, restore the setup script's owner execute
permission before running it:

```sh
chmod u+x scripts/setup_mac.sh
./scripts/setup_mac.sh
```

Alternatively, run the script through Bash without changing its executable
bit:

```sh
bash scripts/setup_mac.sh
```

Do not use `chmod -R 777` on the extracted directory. SpeedyType source and
configuration files do not need to be executable or writable by every user.

## Install or update

Run the one-time setup from the extracted repository:

```sh
./scripts/setup_mac.sh
```

To select a non-default configuration file during installation:

```sh
./scripts/setup_mac.sh "/path/to/other.env"
```

The setup creates or reuses `.venv`, installs `requirements.txt`, and installs
the daily command at `~/.local/bin/speedytype`. It is safe to rerun after an
update. Run it again from the newly extracted release so the command wrapper
points to that release's repository and virtual environment.

## Add the command to zsh PATH

If setup prints a PATH warning, add `~/.local/bin` to `~/.zshrc`. The following
commands create the file if needed, avoid duplicate entries, and update the
current terminal immediately:

```sh
touch ~/.zshrc
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
command -v speedytype
```

Verify that the installed wrapper has execute permission:

```sh
test -x "$HOME/.local/bin/speedytype" && echo "speedytype command is executable"
```

If this prints nothing, rerun `./scripts/setup_mac.sh`. The installer creates
the wrapper with execute permission; manual recursive permission changes are
not required.

## Credentials and configuration permissions

API keys should remain in macOS Keychain through the existing Keyring
integration. The generated wrapper contains only the Python executable,
repository, and default configuration paths. Setup neither copies nor modifies
credentials; the existing Keyring → process environment → legacy `.env`
fallback and migration rules remain unchanged.

If you intentionally use a legacy or custom `.env` file, restrict it to your
user account. For the default legacy path:

```sh
chmod 600 "$HOME/Library/Application Support/SpeedyType/.env"
```

This file only needs read and write permission for its owner. It must not be
made executable. If the file does not exist because all secrets are in
Keychain, no `.env` permission change is needed.

## Permission denied after `chmod`

The extracted directory and its parent directories must allow your user to
read, write, and traverse them. If scripts still cannot run after restoring
their execute permission, check whether the release is on an external drive,
network share, or restricted volume mounted with `noexec`. `chmod` cannot
override a `noexec` mount. Move the complete extracted directory to a local
user-owned location, such as `~/Applications/SpeedyType`, and run setup there.

If macOS Gatekeeper blocks a verified release, first confirm that the archive
came from the expected source and compare its SHA-256 checksum with the
published `SHA256SUMS.txt`. Then use **System Settings > Privacy & Security**
to review and allow the blocked item. Do not broadly remove quarantine
attributes from the entire release directory.

## macOS privacy permissions

Depending on the feature used, macOS may request these permissions under
**System Settings > Privacy & Security**:

- **Accessibility** for keyboard automation.
- **Input Monitoring** for detecting keyboard input and shortcuts.
- **Microphone** for guided recording and transcription input.

Grant access only to the terminal application or Python executable that runs
SpeedyType. A newly extracted release can have a different `.venv/bin/python`
path, so macOS may request permission again after an update. If a feature stops
working after an update, review these three permission lists and reauthorize
the executable for the current release when necessary. Fully stop and restart the daemon
after changing Accessibility or Input Monitoring permission:

```sh
speedytype daemon-stop
speedytype daemon
```

The source-release daemon is an accessory application: normal operation shows
the SpeedyType menu-bar icon and no Python icon in the Dock. Settings and About
opened from that menu-bar icon should be brought to the foreground. A
standalone `speedytype settings` process remains a normal foreground app.

If Python crashes, open **Console > Crash Reports** or inspect
`~/Library/Logs/DiagnosticReports/` for a recent Python .ips report. Preserve
that report together with the SpeedyType daemon log before restarting.

## Daily commands

```sh
speedytype diagnose-config
speedytype daemon
speedytype daemon-stop
speedytype guided-recording --script real_voice_script.md
speedytype --env /path/to/other.env daemon
```

## Monthly usage and budget

Open `speedytype settings` and use `設定月預算` in `本月用量與預算`. The
single budget combines STT and LLM estimates in the currency from
`pricing.json`; it can be adjusted or cleared without changing API pricing.
The month follows the Mac's current local timezone. Values are estimates, not
provider billing or quota, and exceeding the budget does not interrupt
recording or processing. If no percentage is shown, review the visible warning
and confirm that the latency log and `pricing.json` are readable and valid.

## Real Mac verification

The v0.5.4 release candidate must complete all of these checks on the target
Mac; the final tag is blocked until they pass:

1. Update an existing v0.5.3 source install and rerun `./scripts/setup_mac.sh`.
2. Start `speedytype daemon` from a new zsh terminal.
3. Confirm the menu-bar icon appears with no Python icon in the Dock.
4. Open Settings and About from the menu bar and confirm both come forward.
5. Hold and release F9 and confirm there is no macOS warning sound.
6. Complete a normal recording, paste, and clipboard restoration.
7. Tap F9 for less than 0.1 seconds, observe a safe skip, then record normally.
8. Capture F9 and a modified chord in Settings without recording or crashing.
9. Save, restart, and make a recording with the new chord.
10. Complete ten consecutive recording/paste cycles.
11. Use menu-bar Restart and Quit and confirm no Python process is left behind.
12. Run standalone `speedytype settings` and capture a chord.
13. Confirm no new Python `.ips` report appeared during the test period.
14. Open Settings at 520 pixels or wider and confirm the monthly capacity card
   renders, scrolls, and can set then clear a pending budget.

Also rerun setup twice, confirm the PATH entry is not duplicated, confirm the
wrapper is executable, and confirm Keychain credentials remain unchanged. The
script logic and Bash syntax are audited on Windows, but these runtime checks
must be completed on real macOS hardware before v0.5.4 is released.
