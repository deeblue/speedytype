# SpeedyType macOS Setup

Run the one-time setup from the repository:

```sh
./scripts/setup_mac.sh
```

To select a non-default configuration file during installation:

```sh
./scripts/setup_mac.sh "/path/to/other.env"
```

The setup creates or reuses `.venv`, installs `requirements.txt`, and installs
the daily command at `~/.local/bin/speedytype`. It is safe to rerun after an
update.

If setup prints a PATH warning, add this line to `~/.zshrc` for zsh or
`~/.bash_profile` for bash, then open a new terminal:

```sh
export PATH="$HOME/.local/bin:$PATH"
```

Daily examples:

```sh
speedytype diagnose-config
speedytype daemon
speedytype daemon-stop
speedytype guided-recording --script real_voice_script.md
speedytype --env /path/to/other.env daemon
```

The generated wrapper contains only the Python executable, repository, and
default configuration paths. API keys remain in macOS Keychain through the
existing Keyring integration. Setup neither copies nor modifies credentials;
the existing Keyring → process environment → legacy `.env` fallback and
migration rules remain unchanged.

## Real Mac verification

On the target Mac:

1. Run `./scripts/setup_mac.sh` twice.
2. Open a new terminal and run the examples above.
3. Confirm the second setup does not add duplicate PATH entries.
4. Confirm existing Keychain credentials remain available and unchanged.

The script logic and Bash syntax are audited on Windows, but these runtime
checks must be completed on real macOS hardware before describing Mac command
installation as fully verified.
