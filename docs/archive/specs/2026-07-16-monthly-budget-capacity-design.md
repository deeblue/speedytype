# Monthly Budget Capacity Visualization Design

**Date:** 2026-07-16
**Target release:** SpeedyType 0.5.4
**Status:** Approved design, pending implementation plan

## Purpose

The Settings dialog currently renders cumulative STT calls, audio minutes, LLM calls, tokens, and estimated costs as a sequence of text labels. The values are accurate but do not answer the practical capacity question: how much of the user's intended monthly spending has been consumed and how much remains.

This feature replaces the text-heavy presentation with a monthly budget-capacity card. It uses the existing latency CSV and pricing data, remains explicitly an estimate rather than a provider bill, and never blocks recording or API calls.

The approved visual direction is a single combined STT-plus-LLM monthly budget with a progress bar, remaining or exceeded amount, compact STT/LLM usage cards, and separate actions for the personal budget and API pricing.

## Scope

This feature will:

1. add an optional positive monthly budget to application settings;
2. calculate usage and estimated cost for the current local calendar month;
3. show distinct unconfigured, within-budget, over-budget, and unavailable states;
4. show a progress bar only after the user sets a budget;
5. show STT minutes/calls and LLM tokens/calls as compact supporting metrics;
6. provide a dedicated small dialog for setting, changing, or clearing the monthly budget;
7. retain the existing separate price editor;
8. preserve warnings and the pricing update date;
9. document that all values are estimates and that exceeding the budget does not stop SpeedyType.

This feature will not add a default budget, separate STT and LLM budgets, provider billing/quota API integration, automatic enforcement, recording confirmation prompts, daily/weekly trend charts, or a statistics reset operation.

## Data Model

Extend `AppSettings` with an optional `monthly_budget` value. It is serialized as a decimal string so currency math does not pass through binary floating point:

```json
{
  "monthly_budget": "10.00"
}
```

An absent key or empty string means that no budget is configured. Existing `settings.json` files remain valid and load with no budget. A configured value must parse as a finite `Decimal` strictly greater than zero. The budget uses the currency named by the active `pricing.json`; it does not store an independent currency or exchange rate.

The budget dialog displays the active pricing currency, accepts a decimal amount, rejects zero, negative, non-finite, and malformed values inline, and offers a clear action. Accepting the dialog updates the pending Settings state and refreshes the card. The value is persisted only when the parent Settings dialog is saved, so cancelling Settings discards the pending budget change consistently with other settings.

## Monthly Usage Calculation

Keep the existing all-time `calculate_usage()` behavior for current callers and tests. Add a focused monthly calculation interface that reuses the same row validation, pricing, usage, and Decimal cost logic rather than duplicating it.

The current month is defined by the computer's local timezone. Each latency-row ISO 8601 timestamp is parsed as an aware datetime and converted to the local timezone before comparing its year and month. For example, a row at `2026-07-31T16:30:00+00:00` belongs to August on a computer set to Asia/Taipei.

The calculation accepts an injected current datetime/timezone for deterministic tests. Rows with missing, naive, or malformed timestamps cannot be assigned safely to a local month; the monthly view skips them and includes a visible warning count. This does not change their treatment in the existing all-time usage calculation.

The monthly result provides:

- calendar year and month;
- STT calls, minutes, models, and estimated cost;
- LLM calls, input/output tokens, models, and estimated cost;
- combined estimated cost and pricing currency;
- pricing update date;
- usage/pricing availability and warnings.

When both a valid budget and combined cost are available:

```text
percentage = combined estimated cost / monthly budget * 100
remaining = max(monthly budget - combined estimated cost, 0)
exceeded = max(combined estimated cost - monthly budget, 0)
```

The stored percentage is not artificially capped. The progress bar is visually capped at 100%, while the label may show values above 100%.

## Settings Presentation

Replace the current usage-label stack with one focused group titled `本月用量與預算`.

### Budget not configured

Show:

- the current local year/month;
- the month's combined estimated cost;
- `尚未設定月預算`;
- an empty dashed capacity track rather than a percentage;
- STT minutes/calls and LLM total tokens/calls;
- `設定月預算` and `編輯價格` actions;
- pricing date and `估算費用，非實際帳單`.

No arbitrary default percentage or remaining amount is shown.

### Within budget

Show:

- percentage used;
- used amount divided by budget;
- a normal capacity progress bar;
- remaining estimated amount;
- STT and LLM metrics with their estimated cost split;
- `調整月預算` and `編輯價格` actions;
- pricing date and estimate disclaimer.

### Over budget

Show the real percentage above 100%, a visually full red/orange bar, and the estimated exceeded amount. Include a concise warning that SpeedyType will continue to record and process normally. No API call, recording, or paste path reads the budget for enforcement.

### Usage or pricing unavailable

Retain the current visible warning behavior. If monthly usage or combined estimated cost is unavailable, do not calculate a percentage or render a misleading capacity fill. Show the metrics that remain trustworthy, identify the unavailable value, keep both edit actions usable, and preserve detailed warnings without exposing secrets.

The design must remain readable at the dialog's current minimum width of 520 pixels and within its existing scroll area. It must use standard Qt widgets and painting/styles already available through PyQt6; no charting dependency is added.

## Components and Boundaries

- `speedytype/settings.py` owns the optional budget setting, validation, backward-compatible loading, and serialization.
- `speedytype/usage_stats.py` owns local-calendar-month filtering and monthly usage/cost calculation without Qt imports.
- a focused Qt budget dialog owns amount input and validation feedback.
- a focused Qt capacity widget owns the four display states and receives already-calculated values; it does not parse CSV or pricing JSON.
- `speedytype/settings_dialog.py` coordinates pending settings, monthly calculation, refresh after budget or pricing edits, and final save.

The capacity widget and budget dialog should live in focused modules rather than adding another large block to the existing `settings_dialog.py`.

## Error Handling

- Invalid persisted budget values load as unconfigured and produce a visible settings warning rather than preventing Settings from opening.
- Invalid dialog input stays in the dialog with an inline explanation.
- Missing or invalid pricing makes estimated capacity unavailable but does not hide raw usage.
- Missing, invalid, or unreadable latency data uses the existing unavailable/warning semantics.
- Malformed or timezone-unsafe timestamps are skipped only from the monthly result and counted in warnings.
- Saving the budget uses the existing atomic settings-write behavior.
- No error message includes API keys, Keyring values, clipboard content, or transcripts.

## Verification

### Pure calculation tests

- absent and empty budgets load as unconfigured;
- valid decimal strings round-trip exactly;
- zero, negative, non-finite, and malformed budgets are rejected safely;
- an old settings file without the field remains valid;
- local-month filtering handles UTC-to-Asia/Taipei month rollover;
- a different local timezone produces the corresponding month membership;
- malformed, naive, and missing timestamps are skipped with warnings;
- all-time usage totals remain unchanged;
- percentage, remaining, and exceeded values use exact Decimal math;
- percentages above 100% remain above 100 in the result.

### Qt tests

- unconfigured state shows cost, empty track, and `設定月預算`;
- within-budget state shows percentage, fill, and remaining amount;
- over-budget state shows the uncapped percentage, capped warning fill, exceeded amount, and non-blocking copy;
- unavailable state does not render a percentage;
- STT/LLM metrics, pricing date, and disclaimer remain visible where valid;
- budget dialog validates input, clears a budget, and returns a pending value;
- cancelling Settings discards the pending budget;
- saving Settings persists it and reopening displays it;
- editing pricing refreshes the monthly calculation and capacity display;
- the group remains usable at 520-pixel dialog width.

Run the focused settings/usage tests and the complete Windows pytest suite. The feature is platform-neutral, so the same calculation and Qt state tests protect Windows and macOS. The real-Mac 0.5.4 Settings acceptance run must also confirm that the new card renders, scrolls, and edits correctly while the daemon is in accessory mode.

## Documentation and Release

Update `release/README.md`, `MAC_SETUP.md`, and the appropriate project report with:

- how to set, adjust, or clear the monthly budget;
- local-calendar-month semantics;
- the distinction between budget, estimated usage, current pricing data, and actual provider billing;
- the fact that exceeding the budget is informational and never blocks recording;
- unavailable-state troubleshooting for latency or pricing files.

This design has its own implementation plan and testable commits because it is independent of the native macOS keyboard work. Both plans feed the same 0.5.4 release candidate. The final `v0.5.4` release remains blocked until the full Windows suite and the combined real-Mac acceptance checklist pass.

## Acceptance Criteria

- users upgrading without a budget see no invented default or percentage;
- users can set, adjust, and clear one combined monthly budget;
- the current month follows the computer's local timezone;
- the card clearly shows used percentage and remaining or exceeded estimated cost;
- the visual bar caps at 100% while the numeric percentage does not;
- exceeding the budget never blocks or prompts for recording/API operations;
- STT and LLM supporting metrics remain visible and understandable;
- unavailable data never produces a misleading capacity percentage;
- existing settings and all-time usage calculations remain backward compatible;
- no new charting dependency is introduced;
- automated Windows and real-Mac Settings validation pass before 0.5.4 is finalized.
