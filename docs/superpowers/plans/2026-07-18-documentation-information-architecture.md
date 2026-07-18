# Documentation Information Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace scattered SpeedyType documentation with one canonical `docs/` hub, preserve all historical evidence under `docs/archive/`, and keep the generated release bundle compatible.

**Architecture:** Current truth lives only under focused documents in `docs/current/`; dated plans, specs, reports, experiments, and logs live under a clearly non-authoritative `docs/archive/`. The root README becomes a thin developer entry point, while the release builder maps canonical user documents back to the existing release filenames.

**Tech Stack:** Markdown, Python 3.13, pytest, `pathlib`, PowerShell, Git, the existing deterministic release builder.

## Global Constraints

- Implement the approved design in `docs/superpowers/specs/2026-07-18-documentation-information-architecture-design.md` without expanding product scope.
- Preserve historical tracked files through Git-aware renames; do not rewrite archived evidence.
- Move only the seven approved files currently under `docs/log/`; verify resolved paths remain inside the repository before moving them.
- Keep `real_voice_script.md` and `real_voice_script_round2.md` at repository root because they are runtime CLI inputs.
- Keep generated release filenames `README.md`, `MAC_SETUP.md`, and `KNOWN_LIMITATIONS.md` unchanged.
- Current status must say version `0.5.3`, build date `2026-07-16`, target candidate `0.5.4`, Windows automation is completion evidence, macOS is the only hardware release gate, and no 24- or 25-minute live recording is required.
- Archive content is historical and non-authoritative; current product, status, user, architecture, decision, limitation, and release guidance comes only from `docs/current/`.
- Do not add dependencies or modify production recording behavior.
- Perform implementation in an isolated Git worktree created with `superpowers:using-git-worktrees`.

---

## File Structure

**Create:**

- `docs/README.md` — sole repository documentation hub.
- `docs/current/PRODUCT.md` — product purpose, principles, platforms, and success criteria.
- `docs/current/STATUS.md` — live implementation, release-gate, and next-action state.
- `docs/current/engineering/ARCHITECTURE.md` — current runtime data flow and failure boundaries.
- `docs/current/engineering/DECISIONS.md` — concise decision register linked to archived evidence.
- `docs/current/engineering/KNOWN_LIMITATIONS.md` — only limitations that remain true.
- `docs/archive/README.md` — archive authority boundary and category index.
- `tests/test_documentation_structure.py` — structural, link, status-copy, and release-exclusion enforcement.

**Move and update:**

- `release/README.md` → `docs/current/user/README.md` — canonical user guide and release README source.
- `MAC_SETUP.md` → `docs/current/user/MAC_SETUP.md` — canonical macOS setup guide.
- `RELEASE.md` → `docs/current/engineering/RELEASE.md` — canonical developer release procedure.
- `README.md` — rewrite as the thin development-tree entry point.
- `KNOWN_LIMITATIONS.md` → `docs/archive/reports/KNOWN_LIMITATIONS-2026-07-18.md`; create a new current-only limitations document.
- `docs/superpowers/plans/*.md` → `docs/archive/plans/` — completed plans; move this plan only in the final task.
- `docs/superpowers/specs/*.md` → `docs/archive/specs/` — approved/completed specs; move the current architecture spec only in the final task.
- Root plans and reports listed in the approved migration map → matching archive categories.
- Approved `docs/log/*` files → `docs/archive/experiments/long-recording/` or `docs/archive/experiments/macos/`.

**Modify:**

- `scripts/build_release.py` — source release docs from `docs/current/` while retaining destination names.
- `tests/test_build_release.py` — use canonical source paths and verify archive exclusion.
- `tests/test_release_docs.py` — read canonical documents and assert current release-gate language.
- `tests/test_setup_scripts.py` — read canonical macOS setup guide.
- `speedytype/about_dialog.py` and `tests/test_about_dialog.py` — verify the release-facing `KNOWN_LIMITATIONS.md` reference remains unchanged.

---

### Task 1: Lock the Canonical Documentation Contract in Tests

**Files:**

- Create: `tests/test_documentation_structure.py`
- Modify: `tests/test_build_release.py`
- Modify: `tests/test_release_docs.py`
- Modify: `tests/test_setup_scripts.py`

**Interfaces:**

- Consumes: Existing `scripts.build_release.build_release(repo_root, output_root)` and its `ReleaseResult`.
- Produces: Executable path, link, authority, release-content, and obsolete-copy rules used by every migration task.

- [ ] **Step 1: Add failing structure and link tests**

Create `tests/test_documentation_structure.py` with these constants and checks:

```python
from pathlib import Path
import re

import scripts.build_release as build_release


ROOT = Path(__file__).resolve().parent.parent
CANONICAL = {
    "docs/README.md",
    "docs/current/PRODUCT.md",
    "docs/current/STATUS.md",
    "docs/current/user/README.md",
    "docs/current/user/MAC_SETUP.md",
    "docs/current/engineering/ARCHITECTURE.md",
    "docs/current/engineering/DECISIONS.md",
    "docs/current/engineering/KNOWN_LIMITATIONS.md",
    "docs/current/engineering/RELEASE.md",
    "docs/archive/README.md",
}
ALLOWED_ROOT_MARKDOWN = {
    "README.md",
    "real_voice_script.md",
    "real_voice_script_round2.md",
}
LINK_RE = re.compile(r"(?<!!)\[[^]]+\]\(([^)]+)\)")


def test_canonical_documents_exist_and_legacy_trees_are_absent():
    assert all((ROOT / path).is_file() for path in CANONICAL)
    assert not (ROOT / "docs" / "log").exists()
    assert {
        path.name for path in ROOT.glob("*.md")
    } == ALLOWED_ROOT_MARKDOWN


def test_only_active_migration_docs_remain_in_superpowers():
    active = ROOT / "docs" / "superpowers"
    assert {
        path.relative_to(active).as_posix()
        for path in active.rglob("*.md")
    } == {
        "plans/2026-07-18-documentation-information-architecture.md",
        "specs/2026-07-18-documentation-information-architecture-design.md",
    }


def test_current_document_relative_links_resolve():
    for document in (ROOT / "docs" / "current").rglob("*.md"):
        for target in LINK_RE.findall(document.read_text(encoding="utf-8")):
            clean_target = target.split("#", 1)[0]
            if not clean_target or "://" in clean_target or clean_target.startswith("mailto:"):
                continue
            assert (document.parent / clean_target).resolve().exists(), (
                f"broken link in {document.relative_to(ROOT)}: {target}"
            )


def test_documentation_hub_links_every_canonical_destination():
    hub = (ROOT / "docs" / "README.md").read_text(encoding="utf-8")
    for path in sorted(CANONICAL - {"docs/README.md"}):
        relative = Path(path).relative_to("docs").as_posix()
        assert f"]({relative})" in hub


def test_current_status_records_only_macos_hardware_gate():
    current = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (ROOT / "docs" / "current").rglob("*.md")
    )
    status = (ROOT / "docs" / "current" / "STATUS.md").read_text(encoding="utf-8")
    assert "0.5.3" in status
    assert "2026-07-16" in status
    assert "0.5.4" in status
    assert "macOS is the only hardware release gate" in current
    assert "No 24- or 25-minute real recording is required" in current
    assert "Windows Toggle real-device gate is pending" not in current
    assert "≥24-minute" not in current


def test_release_excludes_internal_documentation(tmp_path):
    result = build_release.build_release(ROOT, tmp_path / "dist")
    released = {
        path.relative_to(result.release_dir).as_posix()
        for path in result.release_dir.rglob("*")
        if path.is_file()
    }
    assert {"README.md", "MAC_SETUP.md", "KNOWN_LIMITATIONS.md"} <= released
    assert not any(path.startswith("docs/") for path in released)
    assert not any("archive" in path.lower() for path in released)
```

- [ ] **Step 2: Update existing tests to name the intended canonical paths**

Change document reads as follows while leaving their content assertions intact:

```python
# tests/test_release_docs.py
USER_README = ROOT / "docs" / "current" / "user" / "README.md"
MAC_SETUP = ROOT / "docs" / "current" / "user" / "MAC_SETUP.md"
LIMITATIONS = ROOT / "docs" / "current" / "engineering" / "KNOWN_LIMITATIONS.md"
RELEASE = ROOT / "docs" / "current" / "engineering" / "RELEASE.md"
STATUS = ROOT / "docs" / "current" / "STATUS.md"
ARCHIVED_POC_REPORT = ROOT / "docs" / "archive" / "reports" / "POC_REPORT.md"
```

Replace every old `ROOT / "release" / "README.md"`, root `MAC_SETUP.md`, root `KNOWN_LIMITATIONS.md`, root `RELEASE.md`, and root `POC_REPORT.md` read with the matching constant. In `tests/test_setup_scripts.py`, change the setup-document read to:

```python
content = (
    ROOT / "docs" / "current" / "user" / "MAC_SETUP.md"
).read_text(encoding="utf-8")
```

In `tests/test_build_release.py`, update the reproducibility fixture path to:

```python
second_readme = second_root / "docs" / "current" / "user" / "README.md"
```

- [ ] **Step 3: Run the focused tests and verify they fail for missing canonical paths**

Run:

```powershell
python -m pytest tests/test_documentation_structure.py tests/test_build_release.py tests/test_release_docs.py tests/test_setup_scripts.py -q
```

Expected: failures reference missing `docs/current/*`, `docs/archive/README.md`, and the still-present `docs/superpowers`/root documents; failures must not be syntax or import errors.

- [ ] **Step 4: Commit the executable migration contract**

```powershell
git add tests/test_documentation_structure.py tests/test_build_release.py tests/test_release_docs.py tests/test_setup_scripts.py
git commit -m "test: define canonical documentation structure"
```

---

### Task 2: Archive Tracked Historical Evidence

**Files:**

- Create directories: `docs/archive/plans/`, `docs/archive/specs/`, `docs/archive/reports/`
- Move: all tracked historical plans, specs, and root reports from the approved map.
- Preserve until Task 7: this implementation plan and `2026-07-18-documentation-information-architecture-design.md`.

**Interfaces:**

- Consumes: Exact migration map in the approved design.
- Produces: Stable archive paths for links in `ARCHITECTURE.md` and `DECISIONS.md`.

- [ ] **Step 1: Create archive categories and move completed plans/specs except the two active documents**

Use PowerShell arrays so spaces are not interpreted as separators:

```powershell
New-Item -ItemType Directory -Force docs/archive/plans, docs/archive/specs, docs/archive/reports | Out-Null

Get-ChildItem docs/superpowers/plans -File -Filter *.md |
  Where-Object Name -ne '2026-07-18-documentation-information-architecture.md' |
  ForEach-Object { git mv -- $_.FullName docs/archive/plans/ }

Get-ChildItem docs/superpowers/specs -File -Filter *.md |
  Where-Object Name -ne '2026-07-18-documentation-information-architecture-design.md' |
  ForEach-Object { git mv -- $_.FullName docs/archive/specs/ }
```

- [ ] **Step 2: Move root plans and reports through Git**

```powershell
git mv CROSS_PLATFORM_PLAN.md docs/archive/plans/

$reports = @(
  'COMBINED_LLM_INVESTIGATION_REPORT.md',
  'PHASE2_MODEL_REPORT.md',
  'PHASE3_REPORT.md',
  'PHASE4_REPORT.md',
  'POC_REPORT.md',
  'REAL_VOICE_REPORT.md',
  'REAL_VOICE_REPORT_PHASE2_BASELINE.md',
  'REAL_VOICE_REPORT_PHASE3_DISAMBIG.md',
  'REAL_VOICE_REPORT_ROUND2.md',
  'REAL_VOICE_REPORT_ROUND2_NO_DISAMBIG.md'
)
foreach ($report in $reports) { git mv -- $report docs/archive/reports/ }
git mv KNOWN_LIMITATIONS.md docs/archive/reports/KNOWN_LIMITATIONS-2026-07-18.md
```

- [ ] **Step 3: Verify rename coverage and byte preservation**

Run:

```powershell
git status --short
git diff --summary
git diff --check
```

Expected: the listed files appear as renames or delete/add pairs with identical content; no tracked historical source remains at root; no whitespace errors.

- [ ] **Step 4: Commit tracked archive migration**

```powershell
git add docs/archive
git commit -m "docs: archive completed plans and reports"
```

---

### Task 3: Preserve the Approved Untracked Experiment Logs

**Files:**

- Move: `docs/log/2026-07-16_long-recording*.md` → `docs/archive/experiments/long-recording/`
- Move: `docs/log/mac_log_*.rtf` → `docs/archive/experiments/macos/`

**Interfaces:**

- Consumes: Exactly four Markdown and three RTF files approved by the user.
- Produces: Seven tracked archive artifacts; an absent `docs/log/` tree.

- [ ] **Step 1: Fail closed unless the source inventory is exactly the approved seven files**

Run this from the isolated feature worktree. The approved untracked files remain
in the original main worktree, so verify both roots explicitly:

```powershell
$repo = (Resolve-Path .).Path
$sourceRepo = (Resolve-Path 'C:\WORK\Claude\poc\speedytype').Path
$log = (Resolve-Path (Join-Path $sourceRepo 'docs/log')).Path
if (-not $log.StartsWith($sourceRepo, [System.StringComparison]::OrdinalIgnoreCase)) {
  throw "docs/log resolves outside original worktree: $log"
}
$files = Get-ChildItem -LiteralPath $log -File
$expected = @(
  '2026-07-16_long-recording-hybrid-transcription-investigation.md',
  '2026-07-16_long-recording-layer1-2-implementation-plan.md',
  '2026-07-16_long-recording-layer1-2-implementation-plan v2.md',
  '2026-07-16_long-recording-layer1-2-implementation-plan v3.md',
  'mac_log_000.rtf',
  'mac_log_001.rtf',
  'mac_log_002.rtf'
)
if (Compare-Object ($files.Name | Sort-Object) ($expected | Sort-Object)) {
  throw "docs/log inventory differs from approved seven files"
}
```

Expected: no output and no exception. Stop this task if the inventory differs.

- [ ] **Step 2: Create verified destinations and move using native PowerShell**

```powershell
$longDestination = Join-Path $repo 'docs/archive/experiments/long-recording'
$macDestination = Join-Path $repo 'docs/archive/experiments/macos'
New-Item -ItemType Directory -Force $longDestination, $macDestination | Out-Null
foreach ($destination in @($longDestination, $macDestination)) {
  $resolvedParent = (Resolve-Path (Split-Path $destination -Parent)).Path
  if (-not $resolvedParent.StartsWith($repo, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw "archive destination resolves outside repository: $destination"
  }
}
Get-ChildItem -LiteralPath $log -File -Filter '2026-07-16_long-recording*.md' |
  Move-Item -Destination $longDestination
Get-ChildItem -LiteralPath $log -File -Filter 'mac_log_*.rtf' |
  Move-Item -Destination $macDestination
if (Get-ChildItem -LiteralPath $log -Force) { throw 'docs/log is not empty' }
Remove-Item -LiteralPath $log
```

- [ ] **Step 3: Verify all seven artifacts are present and stage them**

```powershell
if ((Get-ChildItem docs/archive/experiments/long-recording -File).Count -ne 4) { throw 'expected four long-recording documents' }
if ((Get-ChildItem docs/archive/experiments/macos -File).Count -ne 3) { throw 'expected three macOS logs' }
if (Test-Path docs/log) { throw 'docs/log still exists' }
git add docs/archive/experiments
git status --short
```

Expected: four new Markdown files and three new RTF files are staged; `docs/log/` is absent.

- [ ] **Step 4: Commit the approved experiment history**

```powershell
git commit -m "docs: preserve long-recording and macOS experiment logs"
```

---

### Task 4: Create the Canonical Current Documentation Set

**Files:**

- Move: `release/README.md` → `docs/current/user/README.md`
- Move: `MAC_SETUP.md` → `docs/current/user/MAC_SETUP.md`
- Move: `RELEASE.md` → `docs/current/engineering/RELEASE.md`
- Create: `docs/current/PRODUCT.md`
- Create: `docs/current/STATUS.md`
- Create: `docs/current/engineering/ARCHITECTURE.md`
- Create: `docs/current/engineering/DECISIONS.md`
- Create: `docs/current/engineering/KNOWN_LIMITATIONS.md`

**Interfaces:**

- Consumes: Existing operational guides, current source behavior, archived evidence, and fixed status facts from Global Constraints.
- Produces: One authoritative source for each current documentation question and the three release-document inputs.

- [ ] **Step 1: Move the operational source documents to canonical paths**

```powershell
New-Item -ItemType Directory -Force docs/current/user, docs/current/engineering | Out-Null
git mv release/README.md docs/current/user/README.md
git mv MAC_SETUP.md docs/current/user/MAC_SETUP.md
git mv RELEASE.md docs/current/engineering/RELEASE.md
```

- [ ] **Step 2: Consolidate the user guide without dropping tested operational instructions**

Retain all existing installation, dependency, keyring, command-wrapper, update, recording-mode, long-recording, budget, troubleshooting, and checksum content. Organize `docs/current/user/README.md` in this exact order:

```markdown
# SpeedyType User Guide

## What SpeedyType Does
## Supported Platforms
## Install on Windows
## Install on macOS
## Manual Installation
## Update an Existing Installation
## API Keys and the System Keyring
## Daily Commands
## Hold and Toggle Recording Modes
## Long-Recording Safety
## Usage, Budget, and Capacity
## Troubleshooting
## Release Integrity
```

The guide must retain the literal tested commands and phrases from `tests/test_release_docs.py`, including `pip install -r requirements.txt`, `speedytype install-command`, the `--env` override, Hold/Toggle rearm behavior, `25 minutes`, `<23 MiB`, `PCM16 WAV`, `lossless FLAC`, `response_format=json`, `short-WAV fallback`, and `failed-retained`.

- [ ] **Step 3: Preserve and focus the macOS and release guides**

Keep the existing macOS guide operational and standalone. Its heading sequence must cover zsh/unzip permission recovery, Python 3.13, venv/dependencies, command PATH, Keychain, Input Monitoring/Accessibility/Microphone, menu-bar/no-Dock behavior, daemon restart, diagnostics/crash logs, and the bounded-duration real-Mac acceptance gate.

Keep the release checklist's tested version/build, pytest, compileall, builder, annotated tag, master push, tag push, and immutable-tag commands. Add links near the top:

```markdown
Current release state: [STATUS.md](../STATUS.md)

Remaining limitations: [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md)
```

- [ ] **Step 4: Write `PRODUCT.md` and `STATUS.md` as current-only sources**

Use these exact top-level sections:

```markdown
# SpeedyType Product

## Purpose
## User Problem
## Primary Workflow
## Product Principles
## Supported Platforms
## Differentiation
## Success Criteria
```

Describe SpeedyType as a privacy-conscious desktop push-to-talk/toggle transcription and polishing tool that preserves clipboard content, uses OS keyrings, exposes cost/capacity, and fails closed without silently losing recoverable recordings. Avoid market-size, adoption, or unimplemented roadmap claims.

Use this exact status skeleton and facts:

```markdown
# SpeedyType Current Status

**As of:** 2026-07-18  
**Current code version:** 0.5.3  
**Build date:** 2026-07-16  
**Target release candidate:** 0.5.4

## Implemented

- System keyring storage with legacy `.env` migration and pasteable masked key input.
- Windows and macOS short command wrapper and platform-specific daemon integration.
- Hold and Toggle recording modes, elapsed recording overlay, final 60-second countdown, 25-minute automatic stop, and pill-local stop warning.
- Durable PCM16 WAV capture/recovery, validated lossless FLAC conversion, strict `<23 MiB` admission, complete-file `whisper-1` JSON transcription, and retained failure artifacts.
- LLM polishing, clipboard preservation, automatic paste, usage/cost history, monthly budget controls, and capacity visualization.

## Verification State

- Windows simulation and automation are completion evidence; Windows is not a hardware release gate.
- macOS is the only hardware release gate.
- No 24- or 25-minute real recording is required; the macOS gate exercises bounded-duration automatic stop and the documented interaction/permission flow.

## Next Actions

1. Run the documented macOS real-device acceptance procedure.
2. Update `speedytype/version.py` only when cutting the accepted 0.5.4 release.
```

- [ ] **Step 5: Write current architecture, decisions, and limitations**

`ARCHITECTURE.md` must document these stages in order and link each major decision to `DECISIONS.md`: config/keyring resolution → platform hotkey/tray/menu boundary → Hold/Toggle state + overlay → sample-indexed WAV + recovery sidecar → validated lossless FLAC + `<23 MiB` gate → complete-file `whisper-1` JSON → LLM polish → clipboard/paste → usage/capacity record. Include explicit failure boundaries: empty recording does not crash, recoverable WAV is retained, oversize upload fails closed, and startup recovery never silently deletes evidence.

`DECISIONS.md` must use this repeated entry form:

```markdown
## YYYY-MM-DD — Decision title

- **Status:** Accepted
- **Decision:** State the selected production behavior.
- **Rationale:** State the quality, safety, portability, or operability reason.
- **Rejected alternatives:** Name the evaluated alternatives and why they were rejected.
- **Evidence:** Link an exact supporting file under `docs/archive/`.
```

Add entries for keyring migration, allowlisted release + command wrapper, native macOS hotkey/accessory app, complete-file `whisper-1` JSON, durable WAV + validated FLAC + `<23 MiB`, Hold/Toggle + 25-minute ceiling, and Windows automation/macOS-only hardware gate. Every evidence path must name an existing archived file.

`KNOWN_LIMITATIONS.md` must contain only current limitations, each in this form:

```markdown
## Limitation title

- **Impact:** State the user-visible or operational consequence.
- **Workaround:** State the action currently available to the user or operator.
- **Removal condition:** State the evidence or implementation needed to remove the limitation.
```

Derive current entries from the archived snapshot and source behavior; exclude resolved crashes, old implementation chronology, experimental transcript metrics, Windows hardware gates, and any ≥24-minute gate language. Retain current macOS permission/integration uncertainty and the distinction between process/OS-crash durability and unclaimed sudden-power-loss durability.

- [ ] **Step 6: Run content-focused tests and fix only canonical content**

```powershell
python -m pytest tests/test_release_docs.py tests/test_setup_scripts.py tests/test_documentation_structure.py::test_current_status_records_only_macos_hardware_gate -q
```

Expected: all selected tests pass. If a tested phrase is operationally obsolete, reconcile it against the approved spec rather than copying it into multiple current documents.

- [ ] **Step 7: Commit the canonical current sources**

```powershell
git add -A -- docs/current release/README.md MAC_SETUP.md RELEASE.md
git commit -m "docs: establish canonical current documentation"
```

Expected: Git stages moved/current documents; absent legacy paths are recorded without error even if their directories no longer exist.

---

### Task 5: Build the Documentation and Archive Indexes

**Files:**

- Create: `docs/README.md`
- Create: `docs/archive/README.md`
- Modify: `README.md`

**Interfaces:**

- Consumes: Canonical files from Task 4 and stable archive categories from Tasks 2–3.
- Produces: A two-click navigation path from repository root to every canonical document and a clear archive authority boundary.

- [ ] **Step 1: Write the sole documentation hub with direct links to every canonical destination**

Use this link inventory in `docs/README.md`:

```markdown
# SpeedyType Documentation

Use the documents under **Current** for active product, installation, engineering, and release truth. The archive preserves dated evidence and must not be used as current instructions.

## Current

- [Product](current/PRODUCT.md)
- [Status](current/STATUS.md)
- [User guide](current/user/README.md)
- [macOS setup](current/user/MAC_SETUP.md)
- [Architecture](current/engineering/ARCHITECTURE.md)
- [Decision register](current/engineering/DECISIONS.md)
- [Known limitations](current/engineering/KNOWN_LIMITATIONS.md)
- [Release procedure](current/engineering/RELEASE.md)

## Historical Evidence

- [Archive index](archive/README.md)
```

- [ ] **Step 2: Write the archive authority boundary and category index**

Start `docs/archive/README.md` with this exact warning, then list and explain `plans/`, `specs/`, `reports/`, `experiments/long-recording/`, and `experiments/macos/`:

```markdown
# SpeedyType Documentation Archive

> This archive is historical evidence, not current instructions. Dates, paths, gates, and conclusions reflect the time each file was written. Use [`docs/current/`](../current/) for current product and release state.
```

Include direct relative links to each category. State that archived files remain unchanged so Git history and experiment evidence remain auditable.

- [ ] **Step 3: Rewrite the root README as a thin developer entry point**

Retain only: project identity, Python 3.13 venv/dependency setup, `python -m pytest -q`, `python -m compileall -q speedytype scripts`, `python scripts/build_release.py`, the generated `dist/SpeedyType-<version>/` and ZIP locations, a link to `docs/README.md`, and a note that the two real-voice scripts are runtime benchmark inputs. Do not duplicate install, architecture, status, limitations, or release checklist content.

- [ ] **Step 4: Run hub, root-cleanliness, and link tests**

```powershell
python -m pytest tests/test_documentation_structure.py -q
```

Expected: all structure tests pass with the two active migration documents as the only allowed files under `docs/superpowers/`.

- [ ] **Step 5: Commit navigation and root cleanup**

```powershell
git add README.md docs/README.md docs/archive/README.md
git commit -m "docs: add canonical hub and archive index"
```

---

### Task 6: Point the Release Builder at Canonical Sources

**Files:**

- Modify: `scripts/build_release.py`
- Modify: `tests/test_build_release.py`
- Verify: `speedytype/about_dialog.py`
- Modify: `tests/test_about_dialog.py`

**Interfaces:**

- Consumes: Canonical user/release documents from Task 4.
- Produces: An unchanged release-bundle document interface backed by explicit current sources.

- [ ] **Step 1: Change only the release-builder source side of the allowlist**

Replace `STATIC_FILES` entries with:

```python
STATIC_FILES = {
    "docs/current/user/README.md": "README.md",
    "docs/current/user/MAC_SETUP.md": "MAC_SETUP.md",
    "docs/current/engineering/KNOWN_LIMITATIONS.md": "KNOWN_LIMITATIONS.md",
    "requirements.txt": "requirements.txt",
    "pricing.json": "pricing.json",
    ".env.example": ".env.example",
    "real_voice_script.md": "real_voice_script.md",
    "scripts/setup_windows.ps1": "scripts/setup_windows.ps1",
    "scripts/setup_mac.sh": "scripts/setup_mac.sh",
    "scripts/verify_command_alias_windows.ps1": (
        "scripts/verify_command_alias_windows.ps1"
    ),
}
```

Do not add `docs/`, archive, status, architecture, decisions, plans, specs, reports, or experiment artifacts to the release inventory.

- [ ] **Step 2: Verify the About copy remains correct for generated releases**

Do not change the displayed limitations path. Verify the current source still
contains:

```python
"已知限制請見 KNOWN_LIMITATIONS.md",
```

Extend `test_about_dialog_shows_current_config` with:

```python
assert "KNOWN_LIMITATIONS.md" in all_text
```

- [ ] **Step 3: Run release, About, and documentation tests**

```powershell
python -m pytest tests/test_build_release.py tests/test_about_dialog.py tests/test_release_docs.py tests/test_documentation_structure.py -q
```

Expected: all tests pass; the transitional structure assertion still permits exactly the two active migration documents until Task 7.

- [ ] **Step 4: Inspect an actual temporary release inventory**

```powershell
$out = Join-Path $env:TEMP 'speedytype-docs-release-check'
python scripts/build_release.py --output-dir $out
Get-ChildItem -Recurse (Join-Path $out 'SpeedyType-0.5.3') | ForEach-Object FullName
```

Expected: release root contains `README.md`, `MAC_SETUP.md`, and `KNOWN_LIMITATIONS.md`; no `docs`, `archive`, plan, spec, report, experiment, or log path appears.

- [ ] **Step 5: Commit canonical release wiring**

```powershell
git add scripts/build_release.py tests/test_build_release.py tests/test_about_dialog.py
git commit -m "build: source release docs from canonical tree"
```

---

### Task 7: Archive the Completed Design and Plan, Then Verify Everything

**Files:**

- Move: `docs/superpowers/specs/2026-07-18-documentation-information-architecture-design.md` → `docs/archive/specs/`
- Move: `docs/superpowers/plans/2026-07-18-documentation-information-architecture.md` → `docs/archive/plans/`
- Modify: `docs/archive/README.md`

**Interfaces:**

- Consumes: Completed and verified implementation from Tasks 1–6.
- Produces: Final approved tree with no second plan/spec location and a fully passing repository.

- [ ] **Step 1: Move the now-completed active design artifacts and remove empty legacy directories**

```powershell
git mv docs/superpowers/specs/2026-07-18-documentation-information-architecture-design.md docs/archive/specs/
git mv docs/superpowers/plans/2026-07-18-documentation-information-architecture.md docs/archive/plans/
if (Get-ChildItem docs/superpowers -Recurse -Force -File) { throw 'unexpected files remain under docs/superpowers' }
Remove-Item -LiteralPath docs/superpowers/plans
Remove-Item -LiteralPath docs/superpowers/specs
Remove-Item -LiteralPath docs/superpowers
```

- [ ] **Step 2: Change the transitional structure test to require final legacy-tree removal**

Replace `test_only_active_migration_docs_remain_in_superpowers` with:

```python
def test_legacy_documentation_trees_are_absent():
    assert not (ROOT / "docs" / "superpowers").exists()
    assert not (ROOT / "docs" / "log").exists()
```

- [ ] **Step 3: Add the completed information-architecture artifacts to the archive index**

Add direct links under the plan and spec categories:

```markdown
- [Documentation information architecture design](specs/2026-07-18-documentation-information-architecture-design.md)
- [Documentation information architecture implementation plan](plans/2026-07-18-documentation-information-architecture.md)
```

- [ ] **Step 4: Run the complete documentation and release acceptance suite**

```powershell
python -m pytest tests/test_documentation_structure.py tests/test_build_release.py tests/test_release_docs.py tests/test_setup_scripts.py tests/test_about_dialog.py -q
```

Expected: all selected tests pass with no expected failure or skip introduced by this migration.

- [ ] **Step 5: Run the complete project verification**

```powershell
python -m pytest -q
python -m compileall -q speedytype scripts
git diff --check
```

Expected: full pytest passes; compileall exits 0 without output; `git diff --check` exits 0 without output.

- [ ] **Step 6: Audit final paths and worktree state**

```powershell
rg --files -g '*.md' | Sort-Object
rg -n 'release/README|ROOT / "MAC_SETUP.md"|ROOT / "KNOWN_LIMITATIONS.md"|ROOT / "RELEASE.md"|docs/superpowers|docs/log' README.md docs scripts speedytype tests
git status --short
git diff --stat HEAD
```

Expected: only `README.md` and the two runtime scripts are root Markdown; no obsolete source-path reference remains except quoted historical text inside untouched archive files; the worktree contains only the intended migration changes.

- [ ] **Step 7: Commit final archive bookkeeping**

```powershell
git add tests/test_documentation_structure.py docs/archive/README.md docs/archive/plans docs/archive/specs
git commit -m "docs: finalize canonical documentation archive"
```

- [ ] **Step 8: Review commits and prepare integration**

```powershell
git log --oneline --decorate -8
git status --short --branch
```

Expected: the feature branch is clean and contains focused commits for tests, tracked archive migration, approved logs, current docs, indexes, release wiring, and final bookkeeping. Use `superpowers:finishing-a-development-branch` before merging or pushing.
