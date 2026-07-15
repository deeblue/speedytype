# Pasteable Masked API Keys Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make first-run API key fields accept native paste immediately while remaining visually masked by default.

**Architecture:** Keep the existing `MaskedKeyField` and Keyring-backed save path. Store the actual key as the `QLineEdit` text at all times, use Qt echo modes for conceal/reveal, and leave the field editable so standard keyboard and context-menu paste behavior works without custom clipboard code.

**Tech Stack:** Python 3.13, PyQt6 `QLineEdit`, pytest, existing Keyring integration

## Global Constraints

- API key fields are editable immediately and default to `QLineEdit.EchoMode.Password`.
- Show / Hide changes only the echo mode and never changes the actual key text.
- Use Qt's native paste behavior; do not add clipboard monitoring or a custom paste button.
- Existing Keyring persistence, connection tests, save/cancel semantics, and redacted status messages remain unchanged.
- Rebuild the source release and replace its exact checksum evidence after changing released source or documentation.

---

## File Structure

- `speedytype/settings_dialog.py`: owns `MaskedKeyField` editing, echo mode, and value synchronization.
- `tests/test_settings_dialog.py`: proves masked direct paste, visibility toggling, and value preservation.
- `release/README.md`: tells first-time users that keys can be pasted while masked.
- `tests/test_release_docs.py`: enforces the release instruction.
- `POC_REPORT.md`: records the final suite count and regenerated artifact evidence.

### Task 1: Make Masked Key Fields Directly Pasteable

**Files:**
- Modify: `tests/test_settings_dialog.py:1-10,437-455`
- Modify: `speedytype/settings_dialog.py:111-155`

**Interfaces:**
- Consumes: `MaskedKeyField(label: str, initial_value: str, test_func, parent=None)`.
- Produces: an always-editable `line_edit` whose `current_value() -> str` returns pasted or typed text regardless of echo mode.

- [ ] **Step 1: Add the failing direct-paste test and update imports**

Add `QLineEdit` to the existing QtWidgets import and insert this test before the existing reveal-toggle test:

```python
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QLineEdit,
    QPushButton,
    QScrollArea,
)


def test_empty_masked_key_field_accepts_paste_without_reveal(qapp):
    field = MaskedKeyField("OpenAI", "", lambda value: (True, "ok"))
    clipboard = qapp.clipboard()
    previous_text = clipboard.text()
    try:
        clipboard.setText("sk-pasted-first-run-key")

        field.line_edit.setFocus()
        field.line_edit.paste()

        assert not field.line_edit.isReadOnly()
        assert field.line_edit.echoMode() == QLineEdit.EchoMode.Password
        assert field.line_edit.text() == "sk-pasted-first-run-key"
        assert field.current_value() == "sk-pasted-first-run-key"
    finally:
        clipboard.setText(previous_text)
```

- [ ] **Step 2: Run the paste test and verify RED**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_settings_dialog.py::test_empty_masked_key_field_accepts_paste_without_reveal -q
```

Expected: FAIL because the current field is read-only and uses the normal echo mode, so the clipboard value is not pasted.

- [ ] **Step 3: Implement editable password-mode fields**

Remove the now-unused `mask_secret` name from the `speedytype.env_writer`
import, retaining the three connection-test functions:

```python
from speedytype.env_writer import (
    test_gemini_key,
    test_minimax_key,
    test_openai_key,
)
```

Replace the line-edit initialization and `MaskedKeyField` synchronization/toggle methods with:

```python
self.line_edit = QLineEdit()
self.line_edit.setEchoMode(QLineEdit.EchoMode.Password)
self.line_edit.setText(self._value)
layout.addWidget(self.line_edit, 1)


def _sync_value_from_field(self) -> None:
    self._value = self.line_edit.text()


def _toggle_reveal(self) -> None:
    self._sync_value_from_field()
    self._revealed = not self._revealed
    self.line_edit.setEchoMode(
        QLineEdit.EchoMode.Normal
        if self._revealed
        else QLineEdit.EchoMode.Password
    )
    self.toggle_button.setText("隱藏" if self._revealed else "顯示")


def current_value(self) -> str:
    self._sync_value_from_field()
    return self._value
```

Do not call `setReadOnly()` or replace the field text with `mask_secret()` when hiding it.

- [ ] **Step 4: Update the reveal-toggle regression test**

Replace `test_masked_key_field_reveal_toggle_and_edit` with:

```python
def test_masked_key_field_reveal_toggle_and_edit(qapp, tmp_path):
    settings_path = tmp_path / "settings.json"
    save_settings(settings_path, AppSettings())
    dialog = SettingsDialog(
        make_config(), str(tmp_path / ".env"), str(settings_path)
    )

    field = dialog.openai_field
    assert not field.line_edit.isReadOnly()
    assert field.line_edit.echoMode() == QLineEdit.EchoMode.Password
    assert field.line_edit.text() == "sk-test-key-1234"
    assert field.current_value() == "sk-test-key-1234"

    field.toggle_button.click()
    assert field.line_edit.echoMode() == QLineEdit.EchoMode.Normal
    assert field.line_edit.text() == "sk-test-key-1234"

    field.line_edit.setText("sk-brand-new-value")
    field.toggle_button.click()
    assert field.line_edit.echoMode() == QLineEdit.EchoMode.Password
    assert field.line_edit.text() == "sk-brand-new-value"
    assert field.current_value() == "sk-brand-new-value"
```

- [ ] **Step 5: Run Settings and Keyring-focused tests**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_settings_dialog.py tests/test_settings_launcher.py tests/test_secrets_store.py -q
```

Expected: all selected tests pass with zero failures, including direct paste, save-only-changed-key, cancel, connection tests, and Keyring fallback behavior.

- [ ] **Step 6: Commit the behavior change**

```powershell
git add speedytype/settings_dialog.py tests/test_settings_dialog.py
git commit -m "fix: allow paste into masked key fields"
```

### Task 2: Update Release Guidance and Verification Evidence

**Files:**
- Modify: `tests/test_release_docs.py`
- Modify: `release/README.md`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Consumes: the direct-paste `MaskedKeyField` behavior from Task 1 and `python scripts/build_release.py`.
- Produces: user-facing first-run paste guidance and exact evidence for the regenerated `SpeedyType-0.5.0-source.zip`.

- [ ] **Step 1: Add a failing release documentation assertion**

In the existing release README credential test, add:

```python
assert "paste" in content
assert "masked" in content
```

- [ ] **Step 2: Run the documentation test and verify RED**

Run:

```powershell
python -m pytest tests/test_release_docs.py -q
```

Expected: FAIL because the current release README does not explain that masked fields accept direct paste.

- [ ] **Step 3: Document first-run paste behavior**

After the first `speedytype settings` command in `release/README.md`, add:

```markdown
API key fields stay masked but accept typing and native Paste immediately; the
**Show** button is only needed when you want to inspect the entered value.
```

- [ ] **Step 4: Run documentation and focused UI tests**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest tests/test_release_docs.py tests/test_settings_dialog.py tests/test_settings_launcher.py -q
```

Expected: all selected tests pass with zero failures.

- [ ] **Step 5: Run the full suite and regenerate the release twice**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
$first = (Get-FileHash dist/SpeedyType-0.5.0-source.zip -Algorithm SHA256).Hash
python scripts/build_release.py
$second = (Get-FileHash dist/SpeedyType-0.5.0-source.zip -Algorithm SHA256).Hash
if ($first -ne $second) { throw "Release is not reproducible" }
Get-Item dist/SpeedyType-0.5.0-source.zip | Select-Object Length
Get-Content dist/SHA256SUMS.txt
```

Expected: pytest and compileall exit `0`; both builds print the same three output paths; `$first` equals `$second` and the checksum file; record the exact observed test count, duration, ZIP length, and lowercase SHA-256.

- [ ] **Step 6: Replace release evidence with exact observed values**

In `POC_REPORT.md` under **Source release verification evidence**:

- replace the full-suite count and duration with the Step 5 output;
- replace the ZIP byte length with the Step 5 output;
- replace the SHA-256 with the lowercase Step 5 hash;
- add that the first-run masked field accepts native paste before reveal.

Do not change the existing macOS real-device verification boundary.

- [ ] **Step 7: Commit documentation and evidence**

```powershell
git add tests/test_release_docs.py release/README.md POC_REPORT.md
git commit -m "docs: explain masked API key paste"
```

- [ ] **Step 8: Verify committed HEAD and clean status**

Run:

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
python -m pytest -q
python -m compileall -q speedytype scripts
python scripts/build_release.py
git diff --check
git status --short --branch
```

Expected: every command exits `0`, the complete suite has zero failures, and `git status` reports no tracked changes on `master`.
