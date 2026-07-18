# macOS-only Hardware Release Gate Documentation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every plan, release document, and documentation test state that Windows is verified by simulation/automation, no ≥24-minute hardware recording is required, and macOS integration is the only hardware release gate.

**Architecture:** This is a documentation-contract change only. Update historical implementation-plan gate language, user/release documentation, and exact-string tests together; do not change recording, timeout, FLAC, settings, or platform code.

**Tech Stack:** Markdown, pytest documentation-contract tests.

## Global Constraints

- Windows Hold/Toggle, timeout, race, shutdown, recovery, and FLAC behavior are validated by deterministic simulation/automation and are not hardware release gates.
- No 24- or 25-minute real recording is required on Windows or macOS.
- Real macOS integration is the only hardware release gate.
- The macOS gate covers permissions, Hold/Toggle, release/rearm/repress, countdown/automatic stop with a bounded duration, menu-bar/Dock behavior, shutdown, and retained failure recovery.
- File `fsync` improves crash resilience, but sudden-power-loss survival is neither claimed nor a separate release gate.
- Do not modify production Python or platform backend code.

---

### Task 1: Update plans and release documentation contracts

**Files:**
- Modify: `docs/superpowers/plans/2026-07-18-full-file-flac-long-recording.md`
- Modify: `docs/superpowers/plans/2026-07-18-toggle-recording-overlay.md`
- Modify: `release/README.md`
- Modify: `MAC_SETUP.md`
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`
- Modify: `tests/test_release_docs.py`

**Interfaces:**
- Consumes: approved release-gate language in the two design specs.
- Produces: one consistent macOS-only hardware gate contract checked by pytest.

- [ ] **Step 1: Write failing documentation-contract tests**

Replace obsolete assertions with exact positive and negative contracts:

```python
combined = "\n".join((release, setup, limitations, report))
assert "macOS is the only hardware release gate" in combined
assert "Windows simulation/automation" in combined
assert "No 24- or 25-minute real recording is required" in combined
assert "Windows Toggle real-device gate is pending" not in combined
assert "≥24-minute" not in combined
assert "sudden-power-loss real-device gate" not in combined
```

Retain assertions for macOS permissions, Hold/Toggle, menu-bar/Dock, bounded automatic stop, shutdown, retained WAV recovery, and the statement that real-Mac acceptance remains pending.

- [ ] **Step 2: Run the release-doc tests and confirm RED**

Run: `python -m pytest tests/test_release_docs.py -q`

Expected: failures identify obsolete Windows/≥24-minute/sudden-power gate text and missing macOS-only language.

- [ ] **Step 3: Update both implementation plans**

Change only gate statements, preserving completed implementation checkboxes and historical test commands. State Windows automation is completion evidence, remove all ≥24-minute requirements, and make the real macOS integration checklist the only pending hardware gate.

- [ ] **Step 4: Update release, Mac, limitations, and POC documents**

Use these exact relationships everywhere:

- `Windows simulation/automation is completion evidence and is not a hardware release gate.`
- `macOS is the only hardware release gate.`
- `No 24- or 25-minute real recording is required on either platform.`
- `Sudden-power-loss survival is not claimed and is not a separate release gate.`

In `MAC_SETUP.md`, remove the ≥24-minute checklist item and retain a bounded-duration automatic-stop check. Preserve all permission, zsh, unzip, executable-bit, Keychain, menu-bar, no-Dock-icon, crash-report, Toggle, restart, and retained-WAV checks.

- [ ] **Step 5: Run focused and broad verification**

```powershell
python -m pytest tests/test_release_docs.py -q
python -m pytest tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py tests/test_recording_control.py tests/test_overlay.py tests/test_daemon_recovery.py tests/test_flac_upload.py -q
python -m compileall -q speedytype scripts
git diff --check
```

Expected: every command exits 0; no production Python file differs from the pre-task commit.

- [ ] **Step 6: Commit**

```powershell
git add docs/superpowers/plans/2026-07-18-full-file-flac-long-recording.md docs/superpowers/plans/2026-07-18-toggle-recording-overlay.md release/README.md MAC_SETUP.md KNOWN_LIMITATIONS.md POC_REPORT.md tests/test_release_docs.py docs/superpowers/plans/2026-07-18-macos-only-release-gate.md
git commit -m "docs: keep macOS as sole hardware release gate"
```
