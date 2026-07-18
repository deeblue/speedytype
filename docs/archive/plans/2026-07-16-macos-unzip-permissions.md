# macOS Unzip Permissions Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `MAC_SETUP.md` a safe, complete setup guide for users running the macOS default zsh after extracting a SpeedyType source release.

**Architecture:** This is a documentation-only change. One guide will explain the normal installation path first, followed by targeted recovery guidance for stripped executable bits, PATH setup, protected configuration files, `noexec` volumes, Gatekeeper, and macOS runtime privacy permissions.

**Tech Stack:** Markdown, zsh-compatible shell commands, macOS Privacy & Security settings

## Global Constraints

- Modify only `MAC_SETUP.md` during implementation.
- Assume the user runs the macOS default zsh; primary PATH instructions must use `~/.zshrc`.
- Keep Keychain/Keyring as the preferred credential store; `.env` guidance applies only to legacy or explicitly selected configuration files.
- Do not recommend `chmod -R 777` or blanket quarantine removal.
- Do not claim real-Mac verification has occurred.

---

### Task 1: Expand the macOS setup and permissions guide

**Files:**
- Modify: `MAC_SETUP.md`

**Interfaces:**
- Consumes: the existing `scripts/setup_mac.sh` entry point and installed `~/.local/bin/speedytype` wrapper behavior
- Produces: a zsh-first installation and troubleshooting guide; no programmatic interface changes

- [ ] **Step 1: Record the current documentation baseline**

Run:

```powershell
rg -n "bash_profile|zshrc|chmod|noexec|Accessibility|Input Monitoring|Microphone" MAC_SETUP.md
```

Expected: the current guide mentions both `~/.zshrc` and `~/.bash_profile`, but does not yet document the required unzip-permission and macOS privacy cases.

- [ ] **Step 2: Rewrite the setup guide with the approved content**

Update `MAC_SETUP.md` to contain these sections and commands:

1. Explain that Terminal uses zsh by default and recommend extracting to a local user-owned path.
2. Restore the setup script's owner execute bit, then run it:

```sh
chmod u+x scripts/setup_mac.sh
./scripts/setup_mac.sh
```

3. Document the alternative invocation when an extractor stripped the executable bit:

```sh
bash scripts/setup_mac.sh
```

4. Preserve the custom configuration example and quote paths containing spaces:

```sh
./scripts/setup_mac.sh "/path/to/other.env"
```

5. Add the PATH entry idempotently, load it into the current zsh session, and verify the command:

```sh
grep -qxF 'export PATH="$HOME/.local/bin:$PATH"' ~/.zshrc || \
  echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
command -v speedytype
```

6. Verify the installed wrapper is executable and direct the user to rerun setup if the check fails:

```sh
test -x "$HOME/.local/bin/speedytype" && echo "speedytype command is executable"
```

7. Explain that a legacy or explicitly selected `.env` should be owner-only while Keychain remains preferred:

```sh
chmod 600 "$HOME/Library/Application Support/SpeedyType/.env"
```

8. Add troubleshooting for a local user-owned project directory, `noexec` external/network/restricted volumes, and Gatekeeper. Tell users to verify the release source/checksum and use System Settings > Privacy & Security; explicitly warn against `chmod -R 777` and blanket quarantine removal.
9. Document Accessibility, Input Monitoring, and Microphone permissions, including the possibility of reauthorizing a new release's `.venv/bin/python` path.
10. Retain the daily command examples, Keyring explanation, and honest real-Mac verification checklist.

- [ ] **Step 3: Verify required documentation coverage**

Run:

```powershell
$required = @(
  '~/.zshrc',
  'source ~/.zshrc',
  'chmod u+x scripts/setup_mac.sh',
  'bash scripts/setup_mac.sh',
  'command -v speedytype',
  'test -x "$HOME/.local/bin/speedytype"',
  'chmod 600',
  'noexec',
  'Accessibility',
  'Input Monitoring',
  'Microphone',
  'chmod -R 777'
)
$content = Get-Content -Raw MAC_SETUP.md
$required | ForEach-Object { if (-not $content.Contains($_)) { throw "Missing: $_" } }
```

Expected: command exits successfully without a `Missing:` error.

- [ ] **Step 4: Verify scope and existing setup documentation tests**

Run:

```powershell
git diff --check
git status --short
python -m pytest tests/test_setup_scripts.py tests/test_release_docs.py -q
```

Expected: `git diff --check` reports no whitespace errors; only `MAC_SETUP.md` is modified beyond this already committed plan; all selected tests pass.

- [ ] **Step 5: Commit the documentation update**

```powershell
git add MAC_SETUP.md
git commit -m "docs: explain macOS unzip permissions"
```
