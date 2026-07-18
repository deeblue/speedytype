# macOS Python Preflight and 0.5.3 Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make macOS setup reject Python older than 3.13 with safe recovery instructions, upgrade pip before dependency installation, and publish the verified fix as SpeedyType 0.5.3.

**Architecture:** Keep the preflight inside `scripts/setup_mac.sh` so failure occurs before dependency installation or command-alias creation. Validate the selected bootstrap interpreter and the reusable venv interpreter separately, never delete an incompatible venv, and retain `set -euo pipefail`. Use the existing single version source and immutable annotated-tag release workflow for 0.5.3.

**Tech Stack:** Bash, Python 3.13+, pytest, Markdown, reproducible ZIP builder, Git annotated tags

## Global Constraints

- macOS setup requires Python 3.13 or newer.
- `$PYTHON` overrides the default `python3` only when creating `.venv`.
- Never automatically delete or overwrite an incompatible `.venv`.
- Upgrade pip inside the compatible venv before installing `requirements.txt`.
- Install the command alias only after dependency installation succeeds.
- Preserve zsh, unzip permission, Keychain, PATH, Gatekeeper, and privacy guidance.
- Publish the fix as exactly `0.5.3` with annotated tag `v0.5.3`.
- Never move or replace existing tag `v0.5.2`.
- Do not track or package `docs/log/mac_log_000.rtf`.
- Do not push `master` or `v0.5.3` without separate user authorization.

---

### Task 1: Add macOS Python preflight and recovery documentation

**Files:**
- Modify: `tests/test_setup_scripts.py`
- Modify: `scripts/setup_mac.sh`
- Modify: `MAC_SETUP.md`

**Interfaces:**
- Consumes: optional `PYTHON` environment variable, existing `.venv/bin/python`, optional first positional `.env` path
- Produces: a compatible `.venv`, upgraded pip, installed requirements, and the existing `install-command` invocation

- [ ] **Step 1: Add failing setup-script and documentation contracts**

Append these tests to `tests/test_setup_scripts.py`:

```python
def test_macos_setup_enforces_python_313_without_deleting_existing_venv():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    required = (
        'MIN_PYTHON_VERSION="3.13"',
        "sys.version_info >= (3, 13)",
        'check_python_313 "$BOOTSTRAP_PYTHON"',
        'check_python_313 "$VENV_PYTHON"',
        '[[ -d "$VENV_DIR" && ! -x "$VENV_PYTHON" ]]',
        "Existing .venv is incomplete or unusable",
        "brew install python@3.13",
        "brew --prefix python@3.13",
        "Python 3.13 or newer is required",
    )
    for text in required:
        assert text in content

    assert 'rm -rf "$PROJECT_ROOT/.venv"' not in content


def test_macos_setup_upgrades_pip_before_requirements_and_command_alias():
    content = (ROOT / "scripts" / "setup_mac.sh").read_text(encoding="utf-8")

    upgrade = content.index('"$VENV_PYTHON" -m pip install --upgrade pip')
    requirements = content.index(
        '"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"'
    )
    alias = content.index(
        '"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command'
    )

    assert upgrade < requirements < alias


def test_mac_setup_documentation_has_python_313_recovery_flow():
    content = (ROOT / "MAC_SETUP.md").read_text(encoding="utf-8")
    required = (
        "Python 3.13 or newer",
        "python3 --version",
        ".venv/bin/python --version",
        "brew install python@3.13",
        'PYTHON="$(brew --prefix python@3.13)/bin/python3.13"',
        "mv .venv .venv.backup",
    )
    for text in required:
        assert text in content
```

- [ ] **Step 2: Run the new tests and verify RED**

Run:

```powershell
python -m pytest tests/test_setup_scripts.py -q
```

Expected: three new tests fail because the script has no Python preflight or pip upgrade and the guide has no Python recovery section; the existing three tests pass.

- [ ] **Step 3: Implement the safe Python preflight**

Replace `scripts/setup_mac.sh` with:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
ENV_PATH="${1:-$HOME/Library/Application Support/SpeedyType/.env}"
MIN_PYTHON_VERSION="3.13"

check_python_313() {
    local interpreter="$1"
    local version

    if ! command -v "$interpreter" >/dev/null 2>&1; then
        echo "Python executable not found: $interpreter" >&2
        return 1
    fi
    if ! version="$("$interpreter" -c 'import platform; print(platform.python_version())')"; then
        echo "Could not run Python executable: $interpreter" >&2
        return 1
    fi
    if ! "$interpreter" -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 13) else 1)'; then
        echo "Python 3.13 or newer is required; $interpreter reports $version." >&2
        return 1
    fi
}

if [[ -d "$VENV_DIR" && ! -x "$VENV_PYTHON" ]]; then
    cat >&2 <<EOF
Existing .venv is incomplete or unusable. SpeedyType did not modify it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$VENV_DIR" "$VENV_DIR.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

if [[ ! -d "$VENV_DIR" ]]; then
    BOOTSTRAP_PYTHON="${PYTHON:-python3}"
    if ! check_python_313 "$BOOTSTRAP_PYTHON"; then
        cat >&2 <<EOF
Install a compatible Python, then rerun setup:
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
        exit 1
    fi
    "$BOOTSTRAP_PYTHON" -m venv "$VENV_DIR"
fi

if ! check_python_313 "$VENV_PYTHON"; then
    cat >&2 <<EOF
The existing virtual environment is incompatible. SpeedyType did not remove it.
Move it aside, then recreate it with Python 3.13 or newer:
  mv "$PROJECT_ROOT/.venv" "$PROJECT_ROOT/.venv.backup"
  brew install python@3.13
  PYTHON="\$(brew --prefix python@3.13)/bin/python3.13" bash "$PROJECT_ROOT/scripts/setup_mac.sh"
EOF
    exit 1
fi

"$VENV_PYTHON" -m pip install --upgrade pip
"$VENV_PYTHON" -m pip install -r "$PROJECT_ROOT/requirements.txt"
"$VENV_PYTHON" -m speedytype --env "$ENV_PATH" install-command

echo "Setup complete. Open a new terminal and run: speedytype diagnose-config"
```

- [ ] **Step 4: Add Python prerequisite and recovery guidance**

Insert a `## Python prerequisite` section in `MAC_SETUP.md` before `## After extracting the release`. State that Python 3.13 or newer is required and include:

```sh
python3 --version
```

For Homebrew installation and explicit selection include:

```sh
brew install python@3.13
PYTHON="$(brew --prefix python@3.13)/bin/python3.13" bash scripts/setup_mac.sh
```

Explain that setup validates existing environments without deleting them. Add this recovery block:

```sh
.venv/bin/python --version
mv .venv .venv.backup
PYTHON="$(brew --prefix python@3.13)/bin/python3.13" bash scripts/setup_mac.sh
```

State that `mv` preserves the old environment for deliberate inspection/removal and that rerunning setup upgrades pip before requirements.

- [ ] **Step 5: Verify GREEN and Bash syntax**

Run:

```powershell
python -m pytest tests/test_setup_scripts.py -q
bash -n scripts/setup_mac.sh
git diff --check
```

Expected: six setup tests pass, Bash exits `0`, and the diff has no whitespace errors.

- [ ] **Step 6: Commit the setup fix**

```powershell
git add scripts/setup_mac.sh MAC_SETUP.md tests/test_setup_scripts.py
git commit -m "fix: validate macOS Python before setup"
```

### Task 2: Prepare SpeedyType 0.5.3 version contracts and release documentation

**Files:**
- Modify: `tests/test_version.py`
- Modify: `tests/test_build_release.py`
- Modify: `tests/test_release_docs.py`
- Modify: `speedytype/version.py`
- Modify: `RELEASE.md`
- Modify: `release/README.md`

**Interfaces:**
- Consumes: the setup fix from Task 1 and authoritative `speedytype.version.VERSION`
- Produces: package, CLI, About, builder, documentation, and release workflow version `0.5.3`

- [ ] **Step 1: Update tests first for the 0.5.3 contract**

Make these exact replacements:

```text
tests/test_version.py:       0.5.2 -> 0.5.3
tests/test_build_release.py: SpeedyType-0.5.2 -> SpeedyType-0.5.3
tests/test_release_docs.py:  0.5.2/v0.5.2 -> 0.5.3/v0.5.3
```

Keep `BUILD_DATE == "2026-07-16"` unchanged.

- [ ] **Step 2: Run version tests and verify RED**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_version.py tests/test_build_release.py tests/test_release_docs.py -q
```

Expected: failures show runtime/build/checklist output still uses `0.5.2`; unrelated assertions pass.

- [ ] **Step 3: Update the authoritative version and current release docs**

Change `speedytype/version.py` to:

```python
VERSION = "0.5.3"
BUILD_DATE = "2026-07-16"
STT_MODEL = "whisper-1"
```

In `RELEASE.md`, replace every current `0.5.2`/`v0.5.2` command and artifact reference with `0.5.3`/`v0.5.3`. In `release/README.md`, replace both checksum examples with `SpeedyType-0.5.3-source.zip`.

- [ ] **Step 4: Verify the 0.5.3 contracts are GREEN**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_version.py tests/test_build_release.py tests/test_release_docs.py tests/test_about_dialog.py -q
python -m speedytype --version
```

Expected: all selected tests pass and CLI prints exactly `SpeedyType 0.5.3`.

- [ ] **Step 5: Commit the version preparation**

```powershell
git add speedytype/version.py RELEASE.md release/README.md tests/test_version.py tests/test_build_release.py tests/test_release_docs.py
git commit -m "release: prepare SpeedyType 0.5.3 metadata"
```

### Task 3: Build, verify, record, commit, and tag the 0.5.3 release

**Files:**
- Modify: `POC_REPORT.md`
- Generated and ignored: `dist/SpeedyType-0.5.3/`
- Generated and ignored: `dist/SpeedyType-0.5.3-source.zip`
- Generated and ignored: `dist/SHA256SUMS.txt`
- Create Git reference: `refs/tags/v0.5.3`

**Interfaces:**
- Consumes: committed setup fix and 0.5.3 metadata from Tasks 1-2
- Produces: reproducible 0.5.3 source artifact, exact tracked evidence, and annotated local tag

- [ ] **Step 1: Run the complete suite and compilation**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
```

Expected: the complete suite and compilation both exit `0`; record the exact test count and duration.

- [ ] **Step 2: Build twice and require reproducible output**

Run:

```powershell
python scripts/build_release.py
$zip = "dist/SpeedyType-0.5.3-source.zip"
$first = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$firstLength = (Get-Item $zip).Length
python scripts/build_release.py
$second = (Get-FileHash $zip -Algorithm SHA256).Hash.ToLowerInvariant()
$secondLength = (Get-Item $zip).Length
$expected = ((Get-Content -Raw dist/SHA256SUMS.txt).Trim() -split '\s+')[0].ToLowerInvariant()
if ($first -ne $second -or $second -ne $expected -or $firstLength -ne $secondLength) {
    throw "Release is not reproducible"
}
```

Expected: both builds exit `0`; both hashes, lengths, and checksum-file value match. Record the lowercase hash and byte length.

- [ ] **Step 3: Extract and smoke-test the real archive**

Extract into a unique directory beneath `[System.IO.Path]::GetTempPath()`. Before recursive cleanup, resolve the path and require it to remain strictly beneath that temp root. From the extracted `SpeedyType-0.5.3` directory run:

```powershell
python -m compileall -q speedytype
python -m speedytype --version
python -c "import speedytype; print(speedytype.__version__)"
bash -n scripts/setup_mac.sh
```

Parse `scripts/setup_windows.ps1` and `scripts/verify_command_alias_windows.ps1` with `System.Management.Automation.Language.Parser.ParseFile`. Read the released setup and guide and require these strings:

```text
MIN_PYTHON_VERSION="3.13"
sys.version_info >= (3, 13)
"$VENV_PYTHON" -m pip install --upgrade pip
Python 3.13 or newer
brew install python@3.13
mv .venv .venv.backup
```

Expected: CLI prints `SpeedyType 0.5.3`, package prints `0.5.3`, both script parsers succeed, and the released preflight/documentation strings are present.

- [ ] **Step 4: Record exact 0.5.3 evidence**

Update the current version and **Reproducible source release** sections of `POC_REPORT.md` with:

- `VERSION = "0.5.3"` and `BUILD_DATE = "2026-07-16"`;
- exact complete-suite count and duration from Step 1;
- `dist/SpeedyType-0.5.3/` and `dist/SpeedyType-0.5.3-source.zip`;
- exact ZIP byte length and lowercase SHA-256 from Step 2;
- extracted CLI/package versions and successful Mac preflight/documentation audit from Step 3;
- the real Mac 0.5.2 failure cause and that 0.5.3 now fails early with recovery guidance;
- macOS 0.5.3 real-device rerun remains pending.

- [ ] **Step 5: Run fresh pre-commit release verification**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
python -m speedytype --version
git diff --check
git status --short
```

Expected: tests, compilation, build, and diff checks exit `0`; CLI prints `SpeedyType 0.5.3`; tracked changes contain only `POC_REPORT.md`; `docs/log/` remains untracked and is not staged.

- [ ] **Step 6: Commit release evidence**

```powershell
git add POC_REPORT.md
git commit -m "docs: record SpeedyType 0.5.3 release evidence"
```

- [ ] **Step 7: Reverify committed master and create the annotated tag**

Run the complete suite, compilation, release build, version command, and checksum comparison again on committed `master`. Then run:

```powershell
git rev-parse -q --verify refs/tags/v0.5.3 | Out-Null
if ($LASTEXITCODE -eq 0) { throw "Refusing to replace existing tag v0.5.3" }
git tag -a v0.5.3 -m "SpeedyType 0.5.3"
$tagType = (git cat-file -t v0.5.3).Trim()
$tagCommit = (git rev-list -n 1 v0.5.3).Trim()
$masterCommit = (git rev-parse master).Trim()
if ($tagType -ne "tag" -or $tagCommit -ne $masterCommit) {
    throw "v0.5.3 tag verification failed"
}
```

Expected: all verification commands exit `0`; tag type is `tag`; `v0.5.3` points to current `master`; `v0.5.2` remains unchanged; nothing is pushed.
