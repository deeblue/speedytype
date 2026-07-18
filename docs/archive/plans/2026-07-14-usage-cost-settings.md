# Usage and Cost Settings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Record daily STT/LLM usage in the latency CSV and display verified aggregate usage and data-file-driven estimated costs, with a safe price editor in Settings.

**Architecture:** `LatencyRecord` receives provider-reported LLM usage and explicit daily/development scope. `usage_stats.py` is a Qt-independent parser, validator, classifier, and Decimal cost calculator over the CSV plus root `pricing.json`. Settings renders returned totals and edits the same JSON atomically.

**Tech Stack:** Python 3.13, csv/json/decimal standard library, pytest, PyQt6.

## Global Constraints

- Prices exist only in root `pricing.json`; Python contains no fallback price numbers.
- Default programmatic `process_wav()` scope is `development`; daemon/listen/run-once explicitly use `daily`.
- Legacy blank/`hybrid`/`hybrid_fallback` labels count as daily; other legacy non-empty labels do not.
- Provider usage fields are authoritative; do not estimate missing token counts.
- Missing price data makes cost unavailable, never zero.
- UI copy includes `估算費用，非實際帳單，價格可能已變動` and pricing `updated_date`.

---

## File Structure

- `pricing.json`: editable price data and version date.
- `speedytype/paths.py`: root pricing path.
- `speedytype/usage_stats.py`: pricing schema, aggregation dataclasses, CSV classification, Decimal costs, atomic writer.
- `speedytype/latency.py`: new usage/scope CSV columns.
- `speedytype/pipeline.py`: forwards STT model and LLM usage.
- `speedytype/daemon.py`, `speedytype/cli.py`: explicit daily scope.
- `speedytype/settings_dialog.py`: usage group and price-editor launch/refresh.
- `speedytype/pricing_dialog.py`: focused modal numeric editor.
- `tests/test_usage_stats.py`, `tests/test_latency.py`, `tests/test_pipeline_usage.py`, `tests/test_pricing_dialog.py`, `tests/test_settings_dialog.py`: TDD coverage.
- `KNOWN_LIMITATIONS.md`, `POC_REPORT.md`: final evidence.

### Task 1: Pricing schema, path, and pure aggregation

**Files:**
- Create: `pricing.json`
- Create: `speedytype/usage_stats.py`
- Create: `tests/test_usage_stats.py`
- Modify: `speedytype/paths.py`
- Modify: `tests/test_paths.py`

**Interfaces:**
- Produces: `PricingData`, `UsageSummary`, `load_pricing(path)`, `calculate_usage(csv_path, pricing_path)`, `save_pricing(path, data, today=None)`.

- [ ] **Step 1: Write failing pricing and known-fixture aggregation tests**

Use a CSV fixture containing two daily rows, one explicit development row, one excluded legacy benchmark row, and one accepted blank-label legacy row. Hand calculation:

- STT: 2 daily new rows at 60s and 30s plus one 30s legacy row = 2.0 minutes, 3 calls, `$0.012`.
- LLM: only new rows have usage: 1,500 input and 300 output tokens at `$0.25/$1.50` per million = `$0.000825`.
- Total: `$0.012825`.

Assert explicit development and `run_label=real_voice` do not contribute. Add tests for missing price file, malformed JSON, unknown used model, and a malformed numeric CSV row being skipped with one warning.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_usage_stats.py tests/test_paths.py -v`

Expected: import fails because `speedytype.usage_stats` and `default_pricing_path()` do not exist.

- [ ] **Step 3: Implement pricing data and aggregation**

Add root `pricing.json` with `updated_date=2026-07-14`, `currency=USD`, Whisper, both Gemini candidates, three OpenAI candidates, and MiniMax-M3 values from the approved spec.

Implement immutable dataclasses using `Decimal` for prices/costs. `calculate_usage()` must stream `csv.DictReader`, classify scope with:

```python
def is_daily_row(row):
    scope = row.get("usage_scope", "").strip().lower()
    if scope:
        return scope == "daily", False
    return row.get("run_label", "").strip() in {"", "hybrid", "hybrid_fallback"}, True
```

For each accepted row, STT calls equal positive `hybrid_request_count` or 1; audio minutes equal `recording_seconds / 60`. LLM call count increments when `llm_model` is non-empty or legacy `gemini_seconds > 0`. Missing legacy tokens contribute calls but not guessed tokens. A nonzero usage amount with an unknown price marks the corresponding and total cost unavailable.

Add `default_pricing_path()` as `Path(__file__).resolve().parent.parent / "pricing.json"` and assert it in `tests/test_paths.py`.

- [ ] **Step 4: Run pure-module tests**

Run: `python -m pytest tests/test_usage_stats.py tests/test_paths.py -v`

Expected: exact Decimal totals match the hand calculation; all tolerance cases pass.

- [ ] **Step 5: Commit**

```text
git add pricing.json speedytype/usage_stats.py speedytype/paths.py tests/test_usage_stats.py tests/test_paths.py
git commit -m "feat: calculate usage costs from pricing data"
```

### Task 2: Persist provider token usage and daily/development scope

**Files:**
- Modify: `speedytype/latency.py`
- Modify: `speedytype/pipeline.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/cli.py`
- Create: `tests/test_latency.py`
- Create: `tests/test_pipeline_usage.py`
- Modify: `tests/test_hybrid_integration.py`

**Interfaces:**
- Produces: `LatencyRecord` fields `usage_scope`, `stt_model`, `llm_input_tokens`, `llm_output_tokens`, `llm_total_tokens`.
- `process_wav(..., usage_scope: str = "development", stt_model: str = "whisper-1")`.

- [ ] **Step 1: Write failing CSV schema and pipeline propagation tests**

Create an old-schema CSV, append a new record, and assert header migration preserves old values while adding blank new columns. Mock `call_llm_polisher()` with a real `LlmUsage(input_tokens=120, output_tokens=30, total_tokens=150)` and assert both the result record and written CSV contain those values.

Add a call-site test monkeypatching `process_wav` to assert daemon normal/hybrid and CLI `run-once`/`listen` pass `usage_scope="daily"`; existing scripts rely on the default development value.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_latency.py tests/test_pipeline_usage.py tests/test_hybrid_integration.py -v`

Expected: assertions fail because usage fields and `usage_scope` argument do not exist.

- [ ] **Step 3: Add fields and forward authoritative usage**

Append new fields to `LATENCY_FIELDS` and the dataclass with defaults so existing constructors remain compatible. Write integers as blank when `None`, not zero. In the successful LLM path pass `llm_result.usage` values; in empty-transcript path leave token fields `None`. Validate scope against `{"daily", "development"}` in `process_wav()` and raise `ValueError` for any other value.

Change these user paths to daily:

```python
process_wav(..., usage_scope="daily")
```

in daemon normal and hybrid branches plus CLI `run-once` and `listen`. Do not bulk-edit benchmark scripts; their calls remain development by default.

- [ ] **Step 4: Run pipeline/schema tests and full parser regressions**

Run: `python -m pytest tests/test_latency.py tests/test_pipeline_usage.py tests/test_hybrid_integration.py tests/test_llm_retry.py tests/test_parsers.py -v`

Expected: all pass and old CSV migration remains readable.

- [ ] **Step 5: Commit**

```text
git add speedytype/latency.py speedytype/pipeline.py speedytype/daemon.py speedytype/cli.py tests/test_latency.py tests/test_pipeline_usage.py tests/test_hybrid_integration.py
git commit -m "feat: record scoped STT and LLM usage"
```

### Task 3: Settings usage and cost group

**Files:**
- Modify: `speedytype/settings_dialog.py`
- Modify: `tests/test_settings_dialog.py`

**Interfaces:**
- Consumes: `calculate_usage(config.latency_log_path, pricing_path)`.
- Extends: `SettingsDialog(..., pricing_path: str | Path | None = None)` without breaking existing callers.

- [ ] **Step 1: Write failing Qt display tests using the known fixture**

Construct the same fixed CSV/pricing values as Task 1, open `SettingsDialog`, and assert named labels contain `3`, `2.00`, `1,500`, `300`, `$0.012825`, `2026-07-14`, the estimation disclaimer, and the legacy inference note. Add a missing-pricing test asserting `價格資料缺失，無法估算費用` and that calls/minutes/tokens remain visible.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_settings_dialog.py -v`

Expected: constructor rejects `pricing_path` or usage labels are absent.

- [ ] **Step 3: Build the usage group and refresh method**

Add `self.pricing_path`, append `_build_usage_group()` after the keys group, and implement `_refresh_usage()` that calls `calculate_usage()` once on construction. Expose stable testable labels:

- `usage_models_label`
- `usage_stt_label`
- `usage_llm_label`
- `usage_total_label`
- `usage_pricing_note_label`
- `usage_warning_label`

Format currency to six decimal places so small POC costs do not display as `$0.00`. Do not hide usage when costs are unavailable.

- [ ] **Step 4: Run Settings and aggregation tests**

Run: `python -m pytest tests/test_settings_dialog.py tests/test_usage_stats.py -v`

Expected: known fixture and missing-price UI tests pass.

- [ ] **Step 5: Commit**

```text
git add speedytype/settings_dialog.py tests/test_settings_dialog.py
git commit -m "feat: show usage and estimated costs in settings"
```

### Task 4: Atomic price editor

**Files:**
- Create: `speedytype/pricing_dialog.py`
- Create: `tests/test_pricing_dialog.py`
- Modify: `speedytype/usage_stats.py`
- Modify: `speedytype/settings_dialog.py`

**Interfaces:**
- Produces: `PriceEditorDialog(pricing_path, parent=None)`, accepted signal on successful save.
- Consumes/extends: `load_pricing()` and `save_pricing()`.

- [ ] **Step 1: Write failing atomic-save and Qt editor tests**

Test `save_pricing()` rejects negative numbers and leaves the exact original bytes unchanged. Pass a fixed date through a `today` argument and assert successful save changes `updated_date`. In Qt, edit `whisper-1`, click Save, and assert JSON changed; assert every numeric control has minimum `0.0`, so the UI cannot construct a negative price. Add a malformed-source test that shows an error and does not open editable controls.

- [ ] **Step 2: Run and verify RED**

Run: `python -m pytest tests/test_pricing_dialog.py tests/test_usage_stats.py -v`

Expected: imports/functions fail because editor and atomic writer do not exist.

- [ ] **Step 3: Implement atomic writer and focused modal editor**

`save_pricing()` serializes to `path.with_suffix(path.suffix + ".tmp")`, flushes/closes it, and calls `Path.replace(path)` only after complete validation. On any exception it removes only the temp file and re-raises, leaving the original untouched.

`PriceEditorDialog` dynamically creates `QDoubleSpinBox` controls for every existing STT/LLM row, uses range `0..1_000_000` and 8 decimals, and has Save/Cancel buttons. It supports numeric edits only; model add/delete remains manual JSON editing.

Connect Settings `編輯價格` button to the dialog's `exec()`. If accepted, call `_refresh_usage()` immediately.

- [ ] **Step 4: Run editor, Settings, and pure aggregation tests**

Run: `python -m pytest tests/test_pricing_dialog.py tests/test_settings_dialog.py tests/test_usage_stats.py -v`

Expected: atomic failure preservation, date update, JSON edit, and immediate Settings refresh all pass.

- [ ] **Step 5: Commit**

```text
git add speedytype/pricing_dialog.py speedytype/usage_stats.py speedytype/settings_dialog.py tests/test_pricing_dialog.py tests/test_usage_stats.py tests/test_settings_dialog.py
git commit -m "feat: edit pricing data from settings"
```

### Task 5: Documentation and complete verification

**Files:**
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Consumes: all Part A and Part B evidence.
- Produces: exact completion matrix with automated/live distinctions.

- [ ] **Step 1: Run targeted known-data proof**

Run: `python -m pytest tests/test_usage_stats.py tests/test_pipeline_usage.py tests/test_settings_dialog.py tests/test_pricing_dialog.py -v`

Expected: fixed manual totals and UI assertions pass; development calls are excluded.

- [ ] **Step 2: Run the full suite fresh**

Run: `python -m pytest -q`

Expected: zero failures and no unhandled warnings.

- [ ] **Step 3: Run static/syntax and diff checks**

Run: `python -m compileall -q speedytype scripts`

Expected: exit 0. Run: `git diff --check`; expected: exit 0.

- [ ] **Step 4: Update documentation with observed evidence only**

Update limitation 4 and 10 to their post-keyring states. Append Part B to `POC_REPORT.md`: CSV fields, scope policy, exact fixture math, price date/data-file policy, price editor behavior, test command and actual count, plus Windows live keyring/API outcomes from Part A. Mark any external check not actually completed as `NOT_VERIFIED`.

- [ ] **Step 5: Audit the user's completion checklist**

Read the original checklist line-by-line and record PASS/NOT_VERIFIED for: real Windows credential entry, daemon/API resolution, missing keys, Settings masking/test connection, isolated fallback, known cost math, development exclusion, pricing date/disclaimer, and documentation.

- [ ] **Step 6: Commit final evidence**

```text
git add KNOWN_LIMITATIONS.md POC_REPORT.md
git commit -m "docs: report keyring and usage cost verification"
```
