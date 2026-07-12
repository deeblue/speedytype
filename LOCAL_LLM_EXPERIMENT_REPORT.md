# Local Gemma LLM Experiment Report

Date: 2026-07-12

## Scope and evidence

This experiment compared the current online `gemini-3.1-flash-lite` polisher with local Ollama `gemma4:12b` and `gemma4:26b`. It did not change the default provider/model, `.env`, STT, or production behavior. STT remained `whisper-1` throughout; this benchmark exercised only the polishing stage.

The measured evidence is [local_llm_benchmark_results.jsonl](local_llm_benchmark_results.jsonl): Gemini records are lines 1-12, 12B records are lines 13-25, and 26B records are lines 26-38. Cold records are lines 13 and 26; repeated-number records are lines 10-12, 23-25, and 36-38. [local_llm_benchmark_verification.txt](local_llm_benchmark_verification.txt) records the evidence hash, installed model metadata, completeness audit, and test run. Its audit found 38/38 expected unique records with no parse errors, duplicates, missing identities, or unexpected identities; the SHA-256 remained `F26405355269CAC762258E1D73BC5191119BA8FA5F2203DE979D6C3E8485A3F3`.

All warm statistics below use the 12 warm calls per candidate and exclude the separate local cold call. Mean output tokens/second is available only for Ollama because the local response records include evaluation duration. p95 uses the nearest-rank method: sort 12 observations and select rank `ceil(0.95 * 12) = 12`, which is the maximum. This convention is stated because other interpolation methods produce different small-sample values.

## Measured results

| Candidate | Provider calls | Quality passes | Dimension failures | Repeated-number regression | Cold call / model load | Warm mean | Median | Min | Max | p95 | Mean output tok/s |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Gemini Flash-Lite | 12/12 | 12/12 | none | 3/3 pass | not measured | 0.590s | 0.574s | 0.468s | 0.756s | 0.756s | not available |
| Gemma 12B | 13/13 | 10/13 | `extra_ok`: 3 | **0/3 pass** | 42.058s / 16.646s | 27.180s | 29.903s | 5.165s | 42.542s | 42.542s | 4.724 |
| Gemma 26B | 13/13 | 13/13 | none | 3/3 pass | 40.869s / 29.717s | 11.773s | 12.798s | 2.475s | 18.617s | 18.617s | 11.898 |

“Provider calls” measures whether a response arrived without an exception. “Quality passes” measures the deterministic content checks and is not provider reliability. Thus 12B had 13/13 reliable calls but only 10/13 acceptable outputs. Its three repeated-number outputs were identically `123測試 123test`, collapsing the four input occurrences of `123` to two; all three failed `extra_ok` (raw lines 23-25). This is a 0/3 repeated-number result, not a transient call failure. Gemini and 26B each passed all three repetitions (lines 10-12 and 36-38).

The `ollama ps` snapshots recorded 12B at 8.9 GB, 100% CPU, context 4096 (lines 13-25). The 26B snapshots recorded it at 17 GB, 100% CPU, context 4096; the already loaded 12B also remained listed at 8.9 GB during those calls (lines 26-38). These are processor/residency observations at capture time, not system-wide RAM measurements. Verification independently recorded model package sizes of 7.6 GB and 17 GB, Q4_K_M quantization, and parameter counts of 11.9B and 25.8B.

## Cost interpretation

The Gemini records measured 6,099 input and 410 output tokens across 12 calls. A dollar amount is not contained in either evidence artifact, so any online cost is necessarily an estimate using an external tariff. For illustration only, at assumed rates of $0.10 per million input tokens and $0.40 per million output tokens, this run would cost about **$0.000774 total**, or **$0.0000645 per call**. That arithmetic is an inference from measured token counts, not a measured bill, and must be recalculated against the account's actual current pricing.

Ollama incurred zero marginal API fee in this run. That does **not** mean local inference is free: the evidence shows sustained CPU use and substantial model residency, while electricity, hardware purchase/depreciation, and maintenance were not measured.

## Recommendation

**Expose local mode as optional; retain Gemini Flash-Lite as the default.** This is an inference from the measured trade-offs, not a universal conclusion. Gemini matched 26B's 13/13 quality result when the local cold sample is included and was about 20 times faster on warm mean latency (`11.773 / 0.590`). The 26B model is the defensible local option for privacy, offline use, or avoidance of marginal API fees, but its 12.798-second warm median and 40.869-second cold call are poor default interactive behavior on this CPU-only host. The 12B model is not recommended: it was slower than 26B here and failed the repeated-number regression 0/3 despite 13/13 provider reliability.

This small deterministic corpus establishes comparative behavior on one host, not broad production quality or reliability. A future opt-in local release should identify its hardware requirements, make cold-start behavior visible, and repeat quality/latency tests on target machines. No default or production setting is changed by this recommendation.
