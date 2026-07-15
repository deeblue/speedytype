# Versioning and Release Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish SpeedyType `0.5.1` from one authoritative version source, expose it through the package, CLI, About dialog, and source release, and establish a verified annotated-tag release process.

**Architecture:** Keep `speedytype/version.py` as the only literal version source. Package and CLI consumers import `VERSION`; the existing About dialog and release builder continue consuming the same module. A tracked `RELEASE.md` defines the operator-controlled build, verification, merge, tag, and explicit-push boundary.

**Tech Stack:** Python 3.13, argparse, PyQt6, pytest, Git annotated tags, existing reproducible source-release builder

## Global Constraints

- Release version is exactly `0.5.1`; annotated tag is exactly `v0.5.1`.
- Build date is exactly `2026-07-16`.
- `speedytype/version.py` is the only runtime Python source containing the
  literal package version; tests and release documentation may assert the
  current release value.
- `speedytype --version` prints exactly `SpeedyType 0.5.1` plus one newline and exits `0` without loading configuration or credentials.
- About and release builder continue reading the authoritative `VERSION` and `BUILD_DATE` values.
- The release procedure creates an annotated tag only after merge and fresh verification on `master`.
- Never move, replace, or force-update an existing tag.
- Do not push `master` or `v0.5.1` without separate user authorization.
- Preserve the existing macOS real-device verification boundary.

---

## File Structure

- `speedytype/version.py`: sole literal version, build date, and STT metadata.
- `speedytype/__init__.py`: package-facing `__version__` alias imported from `VERSION`.
- `speedytype/cli.py`: root `--version` action.
- `tests/test_version.py`: package and credential-free CLI version contracts.
- `RELEASE.md`: maintained release and annotated-tag operator checklist.
- `tests/test_release_docs.py`: release-checklist documentation contract.
- `tests/test_build_release.py`: current versioned artifact-name contract.
- `release/README.md`: end-user checksum examples for `0.5.1`.
- `POC_REPORT.md`: exact regenerated `0.5.1` artifact and verification evidence.

### Task 1: Unify Runtime Version Consumers

**Files:**
- Create: `tests/test_version.py`
- Modify: `speedytype/version.py`
- Modify: `speedytype/__init__.py`
- Modify: `speedytype/cli.py:1-25,205-210`

**Interfaces:**
- Consumes: `speedytype.version.VERSION: str` and `BUILD_DATE: str`.
- Produces: `speedytype.__version__: str` and root CLI option `speedytype --version`.

- [x] **Step 1: Write failing package and CLI version tests**

Create `tests/test_version.py`:

```python
import pytest

import speedytype
from speedytype import cli
from speedytype.version import BUILD_DATE, VERSION


def test_package_version_uses_authoritative_release_metadata():
    assert VERSION == "0.5.1"
    assert BUILD_DATE == "2026-07-16"
    assert speedytype.__version__ == VERSION


def test_cli_version_exits_without_loading_configuration(monkeypatch, capsys):
    def fail_if_config_load_is_attempted(*args, **kwargs):
        raise AssertionError("--version must not load configuration")

    monkeypatch.setattr(cli, "_load_config_or_print", fail_if_config_load_is_attempted)

    with pytest.raises(SystemExit) as exit_info:
        cli.main(["--version"])

    assert exit_info.value.code == 0
    assert capsys.readouterr().out == "SpeedyType 0.5.1\n"
```

- [x] **Step 2: Run the tests and verify RED**

Run:

```powershell
python -m pytest tests/test_version.py -q
```

Expected: both tests fail under the old implementation: release metadata is
`0.5.0` / `2026-07-10`, package metadata is `0.1.0`, and the CLI does not
recognize `--version` without a required subcommand.

- [x] **Step 3: Update the authoritative release metadata**

Replace `speedytype/version.py` with:

```python
VERSION = "0.5.1"
BUILD_DATE = "2026-07-16"
STT_MODEL = "whisper-1"
```

- [x] **Step 4: Remove the duplicate package version literal**

Replace `speedytype/__init__.py` with:

```python
"""SpeedyType cross-platform voice input."""

from speedytype.version import VERSION


__version__ = VERSION
```

- [x] **Step 5: Add the root CLI version action**

Add this import to `speedytype/cli.py`:

```python
from speedytype.version import VERSION
```

Immediately after constructing the root parser in `build_parser()`, add:

```python
parser.add_argument(
    "--version",
    action="version",
    version=f"SpeedyType {VERSION}",
)
```

Keep `--env` and the required subparsers unchanged after this argument.

- [x] **Step 6: Verify runtime version consumers**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_version.py tests/test_about_dialog.py -q
python -m speedytype --version
```

Expected: `3 passed`; the command prints exactly `SpeedyType 0.5.1` and exits
`0` without requiring `.env` or Keyring credentials.

- [x] **Step 7: Commit runtime version unification**

```powershell
git add speedytype/version.py speedytype/__init__.py speedytype/cli.py tests/test_version.py
git commit -m "feat: unify runtime version metadata"
```

### Task 2: Add the Release Checklist and Versioned Documentation Contracts

**Files:**
- Create: `RELEASE.md`
- Modify: `tests/test_release_docs.py`
- Modify: `tests/test_build_release.py`
- Modify: `release/README.md`

**Interfaces:**
- Consumes: `VERSION == "0.5.1"` from Task 1 and `python scripts/build_release.py`.
- Produces: version-correct end-user guidance and an operator-controlled annotated-tag checklist.

- [x] **Step 1: Write failing release checklist and artifact-name tests**

Append to `tests/test_release_docs.py`:

```python
def test_release_checklist_documents_verified_annotated_tag_workflow():
    content = (ROOT / "RELEASE.md").read_text(encoding="utf-8")
    required = (
        'VERSION = "0.5.1"',
        'BUILD_DATE = "2026-07-16"',
        "python -m pytest -q",
        "python -m compileall -q speedytype scripts",
        "python scripts/build_release.py",
        "git tag -a v0.5.1 -m \"SpeedyType 0.5.1\"",
        "git push origin master",
        "git push origin v0.5.1",
        "Never move or force-update an existing release tag",
    )
    for text in required:
        assert text in content
```

Change the version assertion in
`test_build_release_has_exact_runtime_inventory` to:

```python
assert result.release_dir.name == "SpeedyType-0.5.1"
assert result.archive_path.name == "SpeedyType-0.5.1-source.zip"
```

- [x] **Step 2: Run documentation and builder tests and verify RED**

Run:

```powershell
python -m pytest tests/test_release_docs.py tests/test_build_release.py -q
```

Expected: the checklist test fails because `RELEASE.md` does not exist; after
Task 1 the new artifact-name assertions pass, while the existing `0.5.0`
assertion would no longer match.

- [x] **Step 3: Create the operator release checklist**

Create `RELEASE.md` with this content:

```markdown
# SpeedyType Release Checklist

Release tags are immutable markers of verified `master` commits. Never move or
force-update an existing release tag. Investigate and deliberately correct a
mistaken release instead.

## Prepare the release branch

1. Start from a clean branch based on `master`.
2. Update only the authoritative values in `speedytype/version.py`:

   ```python
   VERSION = "0.5.1"
   BUILD_DATE = "2026-07-16"
   ```

3. Update version-specific release documentation and tests.

## Verify before merge

```powershell
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
$first = (Get-FileHash dist/SpeedyType-0.5.1-source.zip -Algorithm SHA256).Hash
python scripts/build_release.py
$second = (Get-FileHash dist/SpeedyType-0.5.1-source.zip -Algorithm SHA256).Hash
if ($first -ne $second) { throw "Release is not reproducible" }
Get-Content dist/SHA256SUMS.txt
python -m speedytype --version
```

Extract the ZIP in a temporary directory, run Python compilation and
`python -m speedytype --version` from the extracted root, run
`bash -n scripts/setup_mac.sh`, and parse both released PowerShell scripts.

Commit the verified release changes and merge them to `master`.

## Tag the verified master commit

Rerun the complete suite and release build on merged `master`. Confirm that
`v0.5.1` does not already exist, then create and verify the annotated tag:

```powershell
git tag -a v0.5.1 -m "SpeedyType 0.5.1"
git cat-file -t v0.5.1
git rev-list -n 1 v0.5.1
git rev-parse master
```

`git cat-file` must print `tag`; the latter two commit IDs must match.

## Publish only with approval

Do not push a branch or tag until the operator explicitly approves remote
publication. After approval, use:

```powershell
git push origin master
git push origin v0.5.1
```

The local build/tag workflow does not execute either push automatically.
```

- [x] **Step 4: Update end-user checksum examples to `0.5.1`**

In `release/README.md`, replace both occurrences of
`SpeedyType-0.5.0-source.zip` with `SpeedyType-0.5.1-source.zip`, and add
`speedytype --version` to the **Daily commands** block.

Add `"speedytype --version"` to the existing `required` tuple in
`test_release_readme_documents_keyring_usage_and_daily_commands`.

- [x] **Step 5: Verify release documentation and builder contracts**

Run:

```powershell
python -m pytest tests/test_release_docs.py tests/test_build_release.py tests/test_version.py -q
```

Expected: `12 passed` with no failures.

- [x] **Step 6: Commit the release procedure**

```powershell
git add RELEASE.md release/README.md tests/test_release_docs.py tests/test_build_release.py
git commit -m "docs: establish annotated release workflow"
```

### Task 3: Build and Record the `0.5.1` Source Release

**Files:**
- Modify: `POC_REPORT.md`
- Generated and ignored: `dist/SpeedyType-0.5.1/`
- Generated and ignored: `dist/SpeedyType-0.5.1-source.zip`
- Generated and ignored: `dist/SHA256SUMS.txt`

**Interfaces:**
- Consumes: unified version metadata and release procedure from Tasks 1-2.
- Produces: verified `0.5.1` artifacts and exact tracked evidence.

- [x] **Step 1: Run the complete suite and compilation**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
```

Expected: both commands exit `0`; record the exact pytest count and duration.

- [x] **Step 2: Build twice and verify reproducibility**

Run:

```powershell
python scripts/build_release.py
$first = (Get-FileHash dist/SpeedyType-0.5.1-source.zip -Algorithm SHA256).Hash.ToLowerInvariant()
python scripts/build_release.py
$second = (Get-FileHash dist/SpeedyType-0.5.1-source.zip -Algorithm SHA256).Hash.ToLowerInvariant()
$expected = ((Get-Content -Raw dist/SHA256SUMS.txt).Trim() -split '\s+')[0].ToLowerInvariant()
if ($first -ne $second -or $second -ne $expected) { throw "Release hash mismatch" }
Get-Item dist/SpeedyType-0.5.1-source.zip | Select-Object Length
```

Expected: both builds exit `0`, print the same three `0.5.1` output paths, and
all three hashes match. Record the exact lowercase hash and ZIP byte length.

- [x] **Step 3: Extract and smoke-test the real archive**

Extract `dist/SpeedyType-0.5.1-source.zip` into a unique directory beneath the
system temporary directory. Verify the resolved extraction path remains beneath
that temporary root before recursive cleanup. From the extracted
`SpeedyType-0.5.1` root, run:

```powershell
python -m compileall -q speedytype
python -m speedytype --version
bash -n scripts/setup_mac.sh
```

Parse `scripts/setup_windows.ps1` and
`scripts/verify_command_alias_windows.ps1` with
`System.Management.Automation.Language.Parser.ParseFile`. Expected: all checks
exit `0`, CLI output is exactly `SpeedyType 0.5.1`, and cleanup removes only the
guarded temporary extraction directory.

- [x] **Step 4: Replace source-release evidence with exact `0.5.1` results**

In `POC_REPORT.md` under **Reproducible source release** and its evidence:

- record that `speedytype/version.py` is the sole version source for package,
  CLI, About, and release builder;
- record `speedytype --version` output `SpeedyType 0.5.1`;
- replace the suite count/duration with Step 1 output;
- replace every `0.5.0` artifact reference in that section with `0.5.1`;
- replace ZIP length and SHA-256 with Step 2 output;
- record the extracted `0.5.1` CLI smoke result;
- preserve the macOS real-device pending statement.

- [x] **Step 5: Commit exact release evidence**

```powershell
git add POC_REPORT.md
git commit -m "docs: record SpeedyType 0.5.1 release evidence"
```

- [x] **Step 6: Verify committed feature HEAD**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
python -m speedytype --version
git diff --check
git status --short --branch
```

Expected: every command exits `0`; CLI prints `SpeedyType 0.5.1`; the complete
suite has zero failures; the feature worktree has no tracked changes. Do not
create `v0.5.1` on the feature branch.

### Task 4: Tag the Verified Merge Commit

**Files:**
- No tracked file changes.
- Git reference created after local merge: `refs/tags/v0.5.1`.

**Interfaces:**
- Consumes: reviewed feature branch and local-merge choice from branch finishing.
- Produces: annotated local tag `v0.5.1` pointing to verified `master`.

- [x] **Step 1: Merge locally before tagging**

From the main repository root, update and fast-forward merge only after the user
selects local merge:

```powershell
git checkout master
git pull --ff-only
git merge --ff-only feature/versioning-release-0.5.1
```

Expected: merge exits `0`; do not tag if pull or merge fails.

- [x] **Step 2: Reverify merged master and rebuild its release**

Run on `master`:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
python -m speedytype --version
```

Expected: every command exits `0`, CLI prints `SpeedyType 0.5.1`, and the
master-root release hash equals the feature's recorded checksum.

- [x] **Step 3: Refuse an existing tag and create the annotated tag**

Run:

```powershell
git rev-parse -q --verify refs/tags/v0.5.1 | Out-Null
if ($LASTEXITCODE -eq 0) {
    throw "Refusing to replace existing tag v0.5.1"
}
if ($LASTEXITCODE -ne 1) { throw "Unable to inspect existing tags" }
git tag -a v0.5.1 -m "SpeedyType 0.5.1"
```

Expected: the pre-check finds no tag; annotated tag creation exits `0`.

- [x] **Step 4: Verify tag type and target**

Run:

```powershell
$tagType = (git cat-file -t v0.5.1).Trim()
$tagCommit = (git rev-list -n 1 v0.5.1).Trim()
$masterCommit = (git rev-parse master).Trim()
if ($tagType -ne "tag") { throw "v0.5.1 is not annotated" }
if ($tagCommit -ne $masterCommit) { throw "v0.5.1 does not point to master" }
```

Expected: tag type is `tag`; tag and master commit IDs match.

- [x] **Step 5: Clean feature workspace without pushing**

After successful merge, tests, build, and tag verification, remove the owned
`.worktrees/versioning-release-0.5.1` worktree, prune registrations, and delete
the merged feature branch. Verify `dist/SpeedyType-0.5.1-source.zip` remains in
the main repository and report that `master` and `v0.5.1` have not been pushed.
