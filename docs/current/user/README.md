# SpeedyType User Guide

> macOS v0.5.4 release-candidate note: the daemon uses a native Quartz
> keyboard event tap and AppKit accessory policy. Automated contracts pass on
> Windows, but real-Mac acceptance remains pending; do not publish the final
> v0.5.4 tag until the checklist in `MAC_SETUP.md` passes on the target Mac.

## What SpeedyType Does

SpeedyType is a local Windows/macOS voice-input daemon. It records from a
configurable hotkey, transcribes speech, optionally polishes the text, and
pastes the result into the active application.

## Supported Platforms

- Windows 10/11 or a supported macOS version
- Python 3.13 (64-bit recommended)
- A working microphone
- OpenAI plus the selected LLM-provider credentials

Extract the complete release ZIP before running setup. Do not run setup from
inside a ZIP viewer.

## Install on Windows

Open PowerShell in the extracted release directory and run:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/setup_windows.ps1
```

The script creates or reuses `.venv`, runs
`pip install -r requirements.txt`, installs the short `speedytype` command,
and adds its directory to the user PATH when needed. Open a new terminal after
setup.

## Install on macOS

Open Terminal in the extracted release directory and run:

```sh
chmod u+x scripts/setup_mac.sh
./scripts/setup_mac.sh
```

The script creates or reuses `.venv`, installs `requirements.txt`, creates
`~/.local/bin/speedytype`, and reports the exact zsh PATH line if it is needed.
See `MAC_SETUP.md` for unzip permissions, Python selection, macOS privacy
permissions, and the real-device acceptance checklist.

## Manual Installation

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

Open a new terminal after `speedytype install-command` so the updated PATH is
available.

## Update an Existing Installation

Replace the extracted release files with the newer release and rerun the
platform setup script. The venv, dependencies, and command wrapper are
refreshed safely. Keyring credentials are not copied, deleted, or changed by
setup.

## API Keys and the System Keyring

Open Settings before starting the daemon:

```text
speedytype settings
```

API-key fields stay masked but accept typing and native paste immediately;
the **Show** button is only needed to inspect the entered value. Enter the
OpenAI key and the key for the selected LLM provider, test the connections,
and save.

Keys are stored through Keyring in Windows Credential Manager or the macOS Keychain.
Do not put new keys in `.env`; file keys exist only for legacy
fallback and migration. Use `.env.example` as a non-secret configuration
reference.

After saving keys:

```text
speedytype diagnose-config
speedytype daemon
```

The Windows system-tray or macOS menu-bar menu can reopen Settings, restart the
daemon, show About, or exit.

## Daily Commands

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

## Hold and Toggle Recording Modes

Daily daemon recording offers **Hold mode** and **Toggle mode**; the default
recording mode is Hold.

- Hold: press and hold the configured hotkey to record, then release it to
  stop.
- Toggle: press and release once to start; release rearms the shortcut and the
  next press stops exactly once. Duplicate activation while the first press is
  still held is ignored.

Changing the recording mode in Settings requires a daemon restart. The
guided-recording is excluded from these daemon controls and retains its guided
workflow.

While recording, the pill shows elapsed time in `MM:SS`, followed by a final
60-second countdown. At the configured limit, a pill-local automatic-stop
warning remains visible briefly while the normal stop-and-process path starts
in the background.

## Long-Recording Safety

The recording control supports a maximum of **25 minutes**; the default is 60
seconds. SpeedyType always captures mono 16 kHz **PCM16 WAV** first so the
original recording remains recoverable if later processing fails.

After recording stops, SpeedyType encodes a temporary **lossless FLAC** and
verifies its format, exact sample count, and decoded PCM SHA-256. It measures
the actual encoded file and submits one complete-file Whisper request only
when the FLAC is strictly below **23 MiB**, using `response_format=json`
without timestamps.

A **short-WAV fallback** is used only if FLAC preparation fails and the WAV is
itself below the duration and byte guards. Oversize, invalid, transcription,
polishing, and paste failures retain the WAV in SpeedyType's recordings folder
with a `failed-retained` recovery sidecar. On the next daemon start,
SpeedyType reports retained paths but never uploads them automatically.
Post-stop encoding and complete-file transcription can take visible time.

Windows simulation/automation is completion evidence and is not a hardware
release gate. macOS is the only hardware release gate. It covers permissions,
Hold/Toggle behavior, bounded-duration automatic stop, visible pill
transitions, menu-bar/Dock behavior, shutdown, paste, and retained failure
recovery. No 24- or 25-minute real recording is required on either platform.
Sudden-power-loss survival is not claimed and is not a separate release gate.

## Usage, Budget, and Capacity

Settings includes a `本月用量與預算` card. Choose `設定月預算` to enter one
combined STT-and-LLM budget in the currency shown by `pricing.json`; use
`調整月預算` to change or clear it. The card uses the computer's local calendar
month and graphically shows estimated cost, remaining or exceeded capacity,
STT minutes/calls, and LLM tokens/calls.

This is an informational estimate, not an OpenAI or other provider bill or
quota. Exceeding the budget never blocks recording, transcription, or paste.
If latency or pricing data is missing or invalid, the card avoids a misleading
percentage; check its warning, `latency.csv`, and `pricing.json`, then use
`編輯價格` separately from the personal budget.

## Troubleshooting

- Windows: open a new terminal if `speedytype` is not found. Rerun setup to
  refresh the user PATH entry, then run `speedytype diagnose-config`.
- macOS: if requested, add `export PATH="$HOME/.local/bin:$PATH"` to
  `~/.zshrc`, source the file, and open a new terminal.
- macOS: grant Accessibility and Input Monitoring permissions to the selected
  Python executable and Microphone permission when requested. See
  `MAC_SETUP.md` for the real-device checklist.
- Configuration: open `speedytype settings`, save the required keys, and rerun
  `speedytype diagnose-config`.
- Daemon state: use `speedytype daemon-stop` before manually starting another
  daemon instance.

## Release Integrity

Compare the downloaded ZIP SHA-256 with `SHA256SUMS.txt`.

Windows:

```powershell
Get-FileHash SpeedyType-0.5.3-source.zip -Algorithm SHA256
```

macOS:

```sh
shasum -a 256 SpeedyType-0.5.3-source.zip
```

Real macOS runtime verification remains required before describing Mac command
installation as fully verified.
