# Cross-Platform Command Alias Design

## Goal

Provide one-time setup scripts for Windows and macOS that install a short
`speedytype` command. The generated command must invoke the current SpeedyType
Python environment, select the correct default `.env` configuration file,
forward every user argument, and preserve the existing Keyring credential
resolution behavior.

## Scope

This change adds:

- `scripts/setup_windows.ps1` for Windows setup.
- `scripts/setup_mac.sh` for macOS setup.
- `python -m speedytype ... install-command` as the shared installer entry
  point used by both setup scripts.
- A generated `speedytype.bat` on Windows and executable `speedytype` shell
  wrapper on macOS.
- User-level PATH installation or an exact shell PATH instruction.
- Automated platform-neutral tests and live Windows command verification.
- Installation and usage documentation.

This change does not alter daemon autostart, store credentials in wrappers,
add a command uninstaller, or package SpeedyType for PyPI.

## Credential and Configuration Rules

The wrapper contains only:

- The absolute Python executable path selected during setup.
- The absolute default `.env` path selected during setup.
- The fixed `-m speedytype` invocation.

It must never read, expand, copy, log, or persist API key values. Once the CLI
starts, the existing configuration path remains authoritative and the existing
credential resolver continues to use Keyring first, then the process
environment, then legacy `.env` secrets with migration to Keyring.

The wrapper inserts its default as `--env <default-path>` before forwarded
arguments. A user invocation such as `speedytype --env other.env daemon`
therefore supplies a later `--env` value, which `argparse` treats as the
override. Reinstalling the wrapper must not modify the selected `.env` file or
any Keyring entry.

## Shared Installer Boundary

Add `speedytype/command_alias.py` with a small platform-dispatched API:

```python
def install_command_alias(env_path: str | Path | None = None) -> tuple[bool, str]:
    """Install or refresh the current platform's command wrapper."""
```

The module owns wrapper rendering, filesystem installation, executable
permissions, Windows user PATH updates, and PATH-related result messages. The
CLI adds an `install-command` subcommand that calls this API with `args.env`.
Errors are returned as sanitized user-facing messages and a nonzero exit code;
partial wrapper files must not be left behind.

Wrapper content is replaced at the same path on every run. PATH installation
normalizes entries before comparison, so repeated setup never adds duplicate
entries.

## Windows Setup and Wrapper

`scripts/setup_windows.ps1` is the one-time Windows setup entry. It:

1. Resolves the repository root relative to the script.
2. Uses an existing project `.venv` or creates it with the selected Python.
3. Installs `requirements.txt` into that venv.
4. Invokes the venv Python with
   `-m speedytype --env <configured-path> install-command`.
5. Prints the installed wrapper path and tells the user to open a new terminal.

The installer writes `%APPDATA%\SpeedyType\bin\speedytype.bat`. The batch file
quotes the absolute venv Python and `.env` paths, changes to the repository root
so project-relative command inputs retain existing behavior, and forwards `%*`.

The installer updates `HKCU\Environment\Path` without administrator rights.
Comparison is case-insensitive and ignores harmless trailing separators. After
an actual PATH change it broadcasts `WM_SETTINGCHANGE` with `Environment`, so a
new terminal launched from Explorer receives the updated value without logoff
or reboot. Existing terminal processes are not modified.

## macOS Setup and Wrapper

`scripts/setup_mac.sh` is the one-time macOS setup entry. It:

1. Resolves the repository root from the script location without assuming the
   caller's current directory.
2. Creates or reuses `.venv` using `python3`.
3. Installs `requirements.txt` into that venv.
4. Invokes the venv Python with
   `-m speedytype --env <configured-path> install-command`.

The installer writes `~/.local/bin/speedytype` using a safe atomic replacement
and sets executable permissions. The wrapper quotes the venv Python, repository
root, and default `.env` paths and forwards `"$@"` unchanged.

If `~/.local/bin` is absent from the current PATH, setup succeeds but prints
this exact instruction:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

It also identifies `~/.zshrc` for zsh and `~/.bash_profile` for bash as the
appropriate place to persist that line. The setup script does not modify shell
startup files automatically.

## Data Flow

For `speedytype guided-recording --script real_voice_script.md`:

1. The shell locates the generated wrapper through PATH.
2. The wrapper invokes the captured venv Python from the repository root.
3. It supplies `-m speedytype --env <default>` followed by all user arguments.
4. The CLI parses the action and arguments.
5. Configuration loading resolves non-secret settings from the selected file
   and secrets through the existing Keyring-aware resolver.

For `speedytype --env other.env daemon`, the same flow applies except the later
user-provided `--env` replaces the wrapper default.

## Idempotence and Failure Handling

- Re-running either setup script reuses the venv and refreshes the same wrapper.
- Re-running `install-command` does not duplicate the Windows PATH entry.
- Existing unrelated PATH entries retain their order and spelling.
- A wrapper write uses a sibling temporary file followed by replacement.
- Windows registry write or environment broadcast failures return a nonzero
  result with a useful message and no credential data.
- A missing shell PATH entry on macOS is a successful installation with a
  remediation message, because the wrapper itself is installed correctly.

## Verification

Automated tests cover:

- Windows and POSIX wrapper quoting and full argument forwarding.
- Default `.env` insertion and explicit later `--env` override behavior.
- Wrapper output contains no API key values.
- Windows PATH normalization, preservation, deduplication, and repeat install.
- Windows environment-change notification behavior.
- macOS executable permissions, repeat install, and PATH guidance.
- Setup-script repository/venv/path logic.
- `bash -n scripts/setup_mac.sh` where a Bash executable is available.

Live Windows verification runs after installation from newly created `cmd.exe`
processes:

- `speedytype diagnose-config`
- `speedytype daemon`, followed by `speedytype daemon-stop`
- A parameter-bearing command or harmless parser-level equivalent that proves
  arguments reach the CLI unchanged.

The daemon test must use the configured environment, wait for its PID evidence,
and always attempt `daemon-stop` during cleanup. macOS execution remains a
documented real-device verification step because development occurs on
Windows.

## Documentation

Create `MAC_SETUP.md` with macOS setup, PATH guidance, Keyring notes, and alias
examples. Update `POC_REPORT.md` with Windows setup and verification evidence,
including the distinction between the one-time setup scripts and the generated
daily command wrappers.

## Acceptance Criteria

- A new Windows terminal can run `speedytype daemon`, `speedytype daemon-stop`,
  and `speedytype diagnose-config` with behavior equivalent to the full Python
  invocation.
- Windows and macOS wrappers preserve all user arguments.
- `speedytype --env other.env <action>` overrides the installed default.
- No wrapper contains or changes credentials; Keyring remains authoritative.
- Both setup scripts are safe to run repeatedly.
- macOS script syntax and path logic pass Windows-side audit, with real macOS
  execution explicitly left for the user.
- User documentation describes setup and daily usage.
