# Keyring Secrets and Usage Cost Settings Design

**Date:** 2026-07-14

## Purpose

Move `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `MINIMAX_API_KEY` from primary plaintext `.env` storage to the operating system credential store through Python `keyring`, while preserving safe startup fallback behavior. Extend the Settings dialog with daily-dictation STT/LLM usage totals and data-file-driven estimated costs, including a small price editor.

## Scope

This round covers the normal dictation path only: Whisper STT followed by the configured Gemini, OpenAI, or MiniMax text-polishing model. Development scripts, benchmark calls, TTS generation, and prompt experiments are excluded from displayed usage totals.

The implementation retains the latency CSV as the usage source of truth. It does not add a database, a second cumulative counter, billing-provider API integration, periodic resets, or automatic online price updates.

## Secret Storage Architecture

Create `speedytype/secrets_store.py` as the only module that directly calls `keyring`. The service name is `SpeedyType`; credential usernames are `openai_api_key`, `gemini_api_key`, and `minimax_api_key`. The module exposes get, set, delete, and `.env` migration operations without logging secret values.

`speedytype.config.load_config()` parses environment variables and `.env` as it does today, then resolves each API key in this order:

1. Read the corresponding keyring credential.
2. If keyring has no value, use the process environment or `.env` value.
3. If the fallback value came from `.env`, attempt one-time migration to keyring.
4. Immediately read the credential back and compare it with the source value.
5. Only after a successful round-trip verification, remove that specific secret line from `.env`.

Migration is per key. A failure for one provider leaves that provider's `.env` line untouched and does not undo successfully verified migrations for other providers. Keyring backend errors are caught and logged without key material; configuration continues with the environment/`.env` fallback. A successful migration logs `金鑰已遷移至系統保密管理機制` and the provider names only.

The fallback reader remains permanently supported for recovery, portable development, and machines where keyring is unavailable. Normal successful migration removes the plaintext values, so fallback exists as a compatibility path rather than a retained duplicate secret.

OpenAI and Gemini remain required at startup to preserve current behavior. MiniMax remains optional. If required values are unavailable from both keyring and fallback sources, `ConfigError` names the missing variables and tells the user to add them through Settings or `.env`; startup fails cleanly rather than crashing with a backend exception.

## Settings Secret Behavior

The existing masked-last-four display, reveal/hide editing, and test-connection buttons remain unchanged from the user's perspective. Fields are initialized from resolved `AppConfig` values. Test connection continues to use the currently typed value, whether or not it has been saved.

Saving a changed non-empty field writes it to keyring and verifies it by reading it back. Saving a changed empty field deletes that provider credential. Secret changes never call `speedytype.env_writer.update_env_key()`. General settings continue to use `settings.json`; existing `.env` utilities remain available to non-secret configuration paths and tests.

If any secret operation fails, the Settings dialog reports the provider and error, retains the user's field content, and does not claim that provider was saved. It never prints or embeds the secret in an error message.

## Usage Data Collection

Extend `LatencyRecord` and `LATENCY_FIELDS` with:

- `usage_scope`: `daily` or `development`
- `stt_model`
- `llm_input_tokens`
- `llm_output_tokens`
- `llm_total_tokens`

The normal daemon path writes `usage_scope=daily`. Hybrid and hybrid-fallback daemon calls also remain daily. Development and benchmark scripts explicitly use `development`; the safe default for programmatic calls is development so new scripts cannot silently enter user totals. User-facing CLI dictation commands explicitly opt into daily scope.

The existing `LlmResult.usage` provider parsers supply the token fields to `LatencyRecord`; no character-based or tokenizer-based estimate is used. Empty-transcript rows have no LLM call and therefore zero calls/tokens. STT cost uses WAV `recording_seconds` and `stt_model=whisper-1`.

When reading legacy rows without `usage_scope`, the accepted historical inference policy is:

- blank `run_label`, `hybrid`, and `hybrid_fallback` are daily;
- every other non-empty `run_label` is development and excluded.

The UI explains that legacy classification is inferred from `run_label`. Legacy rows without token fields contribute STT calls and minutes but no inferred LLM tokens or cost.

## Pricing Data

Add a standalone repository/application-root `pricing.json` data file with this shape. `speedytype.paths.default_pricing_path()` resolves that file, while Settings and aggregation APIs accept an injected path for tests and alternate deployments:

```json
{
  "updated_date": "2026-07-14",
  "currency": "USD",
  "stt": {
    "whisper-1": {"per_minute": 0.006}
  },
  "llm": {
    "gemini-3.1-flash-lite": {"input_per_million": 0.25, "output_per_million": 1.5},
    "gemini-3.5-flash": {"input_per_million": 1.5, "output_per_million": 9.0},
    "gpt-5.5": {"input_per_million": 5.0, "output_per_million": 30.0},
    "gpt-5.4-mini": {"input_per_million": 0.75, "output_per_million": 4.5},
    "gpt-5.4-nano": {"input_per_million": 0.2, "output_per_million": 1.25},
    "MiniMax-M3": {"input_per_million": 0.3, "output_per_million": 1.2}
  }
}
```

The values are standard pay-as-you-go list prices verified from official provider documentation on the stated date. Python contains field names and formulas only, never fallback price numbers. Missing, unreadable, or invalid pricing data produces an unavailable-cost result with a clear message; it never becomes an implicit zero price.

Create `speedytype/usage_stats.py` to validate pricing, classify CSV rows, aggregate usage, and calculate Decimal-based estimates. It returns structured totals plus warnings, keeping parsing and arithmetic independent of Qt.

## Settings Usage UI

Add a `用量與估算費用` group to `SettingsDialog`, calculated once whenever a new dialog opens. It displays:

- current STT and LLM model names;
- STT call count, total audio minutes, and estimated STT cost;
- LLM polishing call count, total input tokens, total output tokens, and estimated LLM cost;
- total estimated cost;
- pricing `updated_date`;
- `估算費用，非實際帳單，價格可能已變動`;
- the legacy-label inference note when legacy rows were included.

Usage remains visible when a price is missing, while that model's cost is marked unavailable. Malformed individual CSV rows are skipped with a visible warning count. The dialog does not offer a statistics reset; manually archiving or clearing the latency CSV remains the reset mechanism.

## Price Editor

The usage group includes an `編輯價格` button opening a modal editor. It dynamically lists existing STT and LLM entries, allows non-negative numeric editing of per-minute or per-million-token fields, and does not expose source-code constants.

Saving validates every number, writes a complete replacement JSON document to a sibling temporary file, atomically replaces `pricing.json` only after validation and successful serialization, and sets `updated_date` to the current local date. A write failure leaves the original file unchanged and reports the failure. After a successful save, the Settings dialog reloads the file and recalculates displayed costs immediately.

The editor intentionally does not add or delete model rows. Users can add models by editing the plain JSON file directly.

## Error Handling

- Keyring unavailable: retain and use fallback secret; log backend failure without secret content.
- Keyring migration write/read mismatch: do not remove the `.env` line.
- Required key absent everywhere: raise a clear `ConfigError` naming the missing variables and recovery paths.
- Pricing file missing or malformed: show usage, version/cost unavailable, and a readable warning.
- Price absent for one model: aggregate its usage but mark total cost incomplete/unavailable rather than treating it as free.
- Malformed CSV row: skip the row, count it in warnings, and continue processing other rows.
- Old CSV schema: preserve old columns during header migration and leave newly introduced fields blank.

## Testing and Verification

Automated TDD coverage will include:

- fake keyring backend get/set/delete behavior;
- successful `.env` migration with round-trip verification and secret-line removal;
- failed migration preserving `.env` exactly;
- keyring-first config resolution and keyring-empty fallback;
- missing-required-key error without backend crash;
- Settings masked/reveal/edit and test-connection behavior after storage migration;
- Settings changed-key save/delete through keyring and cancel-writes-nothing;
- LLM usage fields reaching newly written latency rows;
- known CSV fixture totals matching hand-calculated STT minutes, token totals, and costs;
- explicit development scope and non-daily legacy labels being excluded;
- legacy daily inference behavior;
- missing/malformed pricing, unknown model, and malformed CSV row tolerance;
- price editor validation, JSON save, date update, and immediate UI refresh.

Secret fallback tests must never delete, overwrite, or substitute any of the three production credential usernames or their real values. Live fallback verification uses a dedicated extra fake username such as `fallback_test_api_key`, a known non-secret value, a temporary `.env`, and an injected test-only secret-name mapping. Cleanup is limited to that exact extra username and temporary file. The production usernames `openai_api_key`, `gemini_api_key`, and `minimax_api_key` are read-only during this test.

Fresh full-suite verification is required before any completion claim. Windows live verification will then attempt to:

1. Run migration against the real configured `.env`.
2. Read the resulting values back through `keyring.get_password()`.
3. Confirm corresponding `SpeedyType` entries in Windows Credential Manager where the environment permits inspection.
4. Run minimal provider connection tests using the resolved daemon configuration.
5. Create the dedicated extra credential `fallback_test_api_key` with a known fake value, use an injected test-only mapping plus a temporary `.env` to verify credential deletion and `.env` fallback, then delete only that extra credential. This step must not delete, overwrite, rename, or substitute `openai_api_key`, `gemini_api_key`, `minimax_api_key`, or any real credential value.

Any live step blocked by absent credentials, network access, Credential Manager visibility, or provider state is reported as not verified. Automated tests do not substitute for those external checks.

## Documentation Changes

Update `KNOWN_LIMITATIONS.md` item 4 to state that OS credential storage is primary and successfully migrated plaintext values are scrubbed, while `.env` remains a compatibility/recovery fallback if a user supplies values there. Update item 10 so it no longer claims Settings writes plaintext secrets. Update `POC_REPORT.md` with architecture, pricing version/source date, migration policy, usage-scope policy, automated test evidence, and exact live-verification results.
