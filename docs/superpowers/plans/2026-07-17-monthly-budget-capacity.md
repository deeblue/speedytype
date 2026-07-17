# Monthly Budget Capacity Implementation Plan

**Goal:** Replace the cumulative text-only usage block with a local-calendar-month budget capacity card while preserving all-time calculation compatibility and keeping the budget informational only.

**Scope guard:** This branch does not change recording, API-call, long-recording, or enforcement behavior.

## Task 1: Persist an optional exact monthly budget

- Add failing settings tests for missing, empty, exact Decimal round-trip, and invalid persisted values.
- Extend `AppSettings` with `monthly_budget: Decimal | None` and non-serialized load warnings.
- Serialize valid budgets as decimal strings; load invalid values as unconfigured with a visible-safe warning.

## Task 2: Calculate current-local-month usage and capacity

- Add failing tests for timezone rollover, alternate timezones, unsafe timestamps, unchanged all-time totals, and exact over-budget math.
- Refactor the existing row accumulator behind `calculate_usage()` without changing its public behavior.
- Add `calculate_monthly_usage()` with injected `now`/timezone and `calculate_budget_capacity()` using `Decimal` throughout.

## Task 3: Add focused Qt components

- Add Qt tests for budget validation/clear and unconfigured, within, over, and unavailable capacity states.
- Implement `BudgetDialog` and `BudgetCapacityWidget` in focused modules.
- Keep the visual fill capped at 100 while displaying the uncapped numeric percentage.

## Task 4: Integrate pending budget state into Settings

- Add tests proving Settings cancel discards pending changes, save persists them, pricing refreshes the card, and the 520-pixel layout remains usable.
- Replace the old usage group with the monthly component, retaining compatibility aliases where useful.
- Surface invalid-budget and skipped-timestamp warnings without exposing sensitive data.

## Task 5: Document and verify

- Update `release/README.md`, `MAC_SETUP.md`, and `POC_REPORT.md` with budget semantics, estimate disclaimers, non-enforcement, and troubleshooting.
- Run focused settings/usage/Qt tests, then the complete Windows suite.
- Record any platform-only real-Mac rendering check as a release gate rather than claiming it was executed on Windows.
