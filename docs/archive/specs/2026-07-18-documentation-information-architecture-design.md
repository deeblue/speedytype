# Documentation Information Architecture Design

**Date:** 2026-07-18

**Status:** Approved design, pending implementation plan

## Goal

Replace SpeedyType's scattered documentation with one navigable source of
truth for current product, user, and engineering information while preserving
all plans, specifications, reports, experiments, and execution logs as
historical evidence.

The reorganization must make current truth easy to find without deleting or
silently rewriting the evidence that produced it. It must also preserve the
clean release bundle: end users receive installation and operating documents,
not internal plans or experiment history.

## Problems Being Solved

The repository currently has more than fifty Markdown files distributed across
the root, `release/`, `docs/superpowers/`, and an untracked `docs/log/` tree.
Current behavior, historical decisions, superseded plans, experiment results,
and release instructions frequently repeat the same subjects with different
dates and conclusions.

As a result:

- readers cannot tell which document is authoritative;
- obsolete release gates and feature states can survive in historical files;
- installation and engineering information are mixed with benchmark evidence;
- updating one feature requires editing several large reports;
- the release builder depends on root-level paths rather than explicit current
  documentation sources.

## Information Architecture

`docs/README.md` is the sole documentation hub. It separates current truth
from historical evidence and links directly to every canonical document.

```text
docs/
  README.md
  current/
    PRODUCT.md
    STATUS.md
    user/
      README.md
      MAC_SETUP.md
    engineering/
      ARCHITECTURE.md
      DECISIONS.md
      KNOWN_LIMITATIONS.md
      RELEASE.md
  archive/
    README.md
    plans/
    specs/
    reports/
    experiments/
      long-recording/
      macos/
```

The repository-root `README.md` remains a short development-tree entry point.
It explains how to install development dependencies, run tests, build a clean
release, and enter the documentation hub. It does not duplicate product,
architecture, or release content.

The runtime content files `real_voice_script.md` and
`real_voice_script_round2.md` remain at the repository root because they are
CLI input assets, not documentation sources. They are explicitly exempt from
the root-document cleanliness rule.

## Canonical Document Responsibilities

### `docs/current/PRODUCT.md`

Defines why SpeedyType exists, the user problem, primary usage, product
principles, supported platforms, differentiation, and success criteria. It is
the only product-vision source.

The initial content is synthesized conservatively from existing release and
cross-platform goals. It must distinguish current facts from proposed future
outcomes and must not invent market claims.

### `docs/current/STATUS.md`

Contains the live version/build date, implemented feature summary, automated
verification status, sole pending hardware release gate, and concise next
actions. It is the only source for "what is complete now?"

At migration time it must state:

- current code version `0.5.3`, build date `2026-07-16`;
- target candidate `0.5.4`;
- complete-file FLAC, recovery, Hold/Toggle, overlay, keyring, usage/capacity,
  command wrapper, and cross-platform platform boundaries are implemented;
- Windows simulation/automation is completion evidence and is not a hardware
  release gate;
- macOS integration is the only hardware release gate;
- no 24- or 25-minute live recording is required.

### `docs/current/user/README.md`

Is the canonical install, update, credential, daily-command, recording-mode,
long-recording safety, budget, and troubleshooting guide. It replaces
`release/README.md` as the source file, while the release builder still copies
it to `README.md` in the generated bundle.

### `docs/current/user/MAC_SETUP.md`

Is the canonical macOS zsh, unzip permission, Python, venv, PATH, Keychain,
privacy permission, menu-bar/Dock, crash-log, and real-Mac acceptance guide.
It replaces the root `MAC_SETUP.md` and is copied to the release bundle root.

### `docs/current/engineering/ARCHITECTURE.md`

Describes the current system only:

- settings/keyring/config resolution;
- Windows/macOS platform boundaries;
- Hold/Toggle recording state and overlay;
- sample-indexed WAV capture and recovery sidecars;
- WAV to validated lossless FLAC to complete-file JSON STT;
- LLM polishing, clipboard preservation, paste, latency/usage records;
- startup recovery and failure boundaries.

It links to archived designs for evidence but does not reproduce experiment
history.

### `docs/current/engineering/DECISIONS.md`

Is a concise decision register. Each entry has date, status, decision,
rationale, rejected alternatives, and links to archived evidence. Initial
entries cover at least:

- system keyring with legacy `.env` migration;
- clean allowlisted source release and short command wrapper;
- native macOS hotkey/accessory application direction;
- complete-file `whisper-1` JSON over segmented/hybrid production;
- durable WAV plus validated lossless FLAC and strict `<23 MiB` admission;
- Hold/Toggle modes with a 25-minute product ceiling;
- Windows automation and macOS-only hardware gate.

### `docs/current/engineering/KNOWN_LIMITATIONS.md`

Contains only limitations that remain true. Resolved problems, implementation
chronology, experiment metrics, and old gate narratives move to archive through
their original reports. Each current limitation includes impact, workaround,
and removal condition.

### `docs/current/engineering/RELEASE.md`

Is the sole developer release procedure: version/build update, test commands,
release builder, reproducibility/checksum, macOS gate, tag, and push sequence.
It replaces the root `RELEASE.md`.

## Archive Policy

`docs/archive/README.md` prominently states:

- archive content is historical evidence, not current instructions;
- dates and conclusions reflect the time of writing;
- current product and release state comes only from `docs/current/`;
- archived paths may be cited from decisions and architecture documents.

Archived files are moved without content rewriting. This preserves their
evidentiary value and lets Git history show renames for tracked files. Future
corrections to current truth must update canonical documents, not old reports.

New completed plans/specs are moved to archive as the final step of the work
that implements them. New experiments enter `docs/archive/experiments/` with a
dated filename and may never become a second current-status document.

## Exact Migration Map

### Current canonical sources

| Existing path | Destination/action |
|---|---|
| `README.md` | Rewrite as thin development and documentation entry point |
| `release/README.md` | Move to `docs/current/user/README.md`, then consolidate |
| `MAC_SETUP.md` | Move to `docs/current/user/MAC_SETUP.md` |
| `KNOWN_LIMITATIONS.md` | Replace with current-only `docs/current/engineering/KNOWN_LIMITATIONS.md`; archive the original snapshot under reports |
| `RELEASE.md` | Move to `docs/current/engineering/RELEASE.md` |

Before replacing the limitations source, its complete original content is
preserved at `docs/archive/reports/KNOWN_LIMITATIONS-2026-07-18.md`.

### Tracked development history

| Existing path/pattern | Destination |
|---|---|
| `docs/superpowers/plans/*.md` | `docs/archive/plans/` |
| `docs/superpowers/specs/*.md` | `docs/archive/specs/` |
| `CROSS_PLATFORM_PLAN.md` | `docs/archive/plans/` |
| `POC_REPORT.md` | `docs/archive/reports/` |
| `PHASE2_MODEL_REPORT.md` | `docs/archive/reports/` |
| `PHASE3_REPORT.md` | `docs/archive/reports/` |
| `PHASE4_REPORT.md` | `docs/archive/reports/` |
| `REAL_VOICE_REPORT*.md` | `docs/archive/reports/` |
| `COMBINED_LLM_INVESTIGATION_REPORT.md` | `docs/archive/reports/` |

### Approved untracked history

| Existing path/pattern | Destination |
|---|---|
| `docs/log/2026-07-16_long-recording*.md` | `docs/archive/experiments/long-recording/` |
| `docs/log/mac_log_*.rtf` | `docs/archive/experiments/macos/` |

The empty `docs/log/` directory is removed after all seven known files are
moved. Before moving, implementation verifies that the resolved source and
destination paths remain within the repository. No unrelated untracked file is
deleted.

## Release Builder and Application References

`scripts/build_release.py` changes its allowlist sources to:

```python
"docs/current/user/README.md": "README.md"
"docs/current/user/MAC_SETUP.md": "MAC_SETUP.md"
"docs/current/engineering/KNOWN_LIMITATIONS.md": "KNOWN_LIMITATIONS.md"
```

Generated release filenames remain unchanged, preserving the end-user
interface. Archive, status, architecture, decisions, reports, plans, and specs
are excluded from the bundle.

Tests and application copy that name old source paths are updated. The About
dialog continues to direct release users to `KNOWN_LIMITATIONS.md`; development
documentation links point to the canonical engineering path.

## Linking and Duplication Rules

- Current documents use repository-relative links and may link into archive for
  evidence.
- Archive documents are not rewritten merely to repair historical relative
  links after a move; `docs/archive/README.md` provides the lookup boundary.
- Current documents must not copy long experiment tables or chronological
  implementation narratives.
- Repository version, current gate, and next-action statements belong in
  `STATUS.md`. The release user guide remains standalone and may repeat only
  the minimum compatibility or acceptance warning needed outside the repository.
- Release-bundle documents may repeat only the minimum operational warning
  required for an end user who does not have the repository documentation.

## Automated Enforcement

Add `tests/test_documentation_structure.py` to verify:

- all canonical files and both archive indexes exist;
- obsolete root report/setup/release/limitations files are absent;
- `docs/superpowers/` and `docs/log/` are absent after migration;
- root Markdown is limited to `README.md` and the two runtime voice scripts;
- every relative Markdown link in current docs resolves, ignoring external URLs
  and in-page anchors;
- `docs/README.md` links to every canonical current document and archive index;
- current docs contain no obsolete Windows or ≥24-minute release-gate claims;
- archive files are not present in a built release.

Update existing release/documentation tests to use canonical source paths.
Run the release builder in a temporary output directory and assert the bundle
still contains `README.md`, `MAC_SETUP.md`, and `KNOWN_LIMITATIONS.md` with the
expected current content.

## Migration Order

1. Add failing structure, link, and release-source tests.
2. Create archive directories and move historical tracked files with Git-aware
   renames.
3. Move the approved untracked `docs/log/` files after path verification.
4. Create canonical documents and archive/current indexes.
5. Update root README, release builder, tests, code copy, and all current links.
6. Run link/structure/release tests, complete pytest, compileall, and diff check.
7. Move this completed spec and its implementation plan into archive as final
   bookkeeping, update indexes, and re-run documentation tests.

## Acceptance Criteria

- `docs/README.md` is the only documentation hub and reaches every current
  document within two clicks.
- Each current question has exactly one canonical source.
- Historical evidence is preserved under `docs/archive/` and clearly labeled
  non-authoritative.
- The repository root contains no Phase, POC, Mac setup, release checklist, or
  limitations reports.
- Release ZIP contents and filenames remain compatible while sourcing documents
  from `docs/current/`.
- All approved `docs/log/` files are archived; none are lost.
- Current status clearly states version `0.5.3`, target `0.5.4`, and the sole
  macOS hardware release gate with no minimum live duration.
- Documentation structure, links, release build, full tests, compileall, and
  `git diff --check` pass.
