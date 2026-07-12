# Local Gemma LLM Experiment Report

Date: 2026-07-12

## Scope and evidence

This polishing-only experiment compared `gemini-3.1-flash-lite` with local Ollama `gemma4:12b` and `gemma4:26b`. STT remained OpenAI `whisper-1`. It did not change `.env`, the default provider/model, or production behavior.

The controlled evidence is [local_llm_benchmark_results.jsonl](local_llm_benchmark_results.jsonl), SHA-256 `B8466AD25190A800ED4748E617BB38460A0C063004C01188DD9AF70C1AC02019`. [local_llm_benchmark_verification.txt](local_llm_benchmark_verification.txt) records commands, timing, prerequisites, isolation, and completeness. The audit found 38/38 expected unique records, no malformed/duplicate/missing/unexpected records, and zero `ollama ps` snapshots containing both local candidates.

Warm statistics use 12 warm trials per candidate. Local cold trials are separate. p95 is nearest-rank (`ceil(0.95 * 12)`, the maximum).

## Measured results

| Candidate | Calls | Warm quality | Dimension failures | Number regression | Cold / load | Warm mean | Median | Min | Max/p95 | Mean tok/s |
|---|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|
| Gemini Flash-Lite | 12/12 | 12/12 | none | 3/3 | not measured | 0.636s | 0.602s | 0.582s | 0.776s | unavailable |
| Gemma 12B | 13/13 | 9/12 | `extra_ok`: 3 | 0/3 | 38.980s / 12.535s | 27.255s | 29.980s | 5.037s | 42.403s | 4.758 |
| Gemma 26B | 13/13 | 12/12 | none | 3/3 | 37.355s / 24.640s | 12.883s | 14.380s | 2.433s | 19.850s | 11.792 |

All provider calls returned successfully; quality is a separate deterministic content gate. 12B failed all repeated-number trials by collapsing content, while Gemini and 26B passed all three. The isolated snapshots measured 12B at 8.9 GB and 26B at 17 GB, each at 100% CPU and context 4096. These are point-in-time Ollama residency observations, not total system RAM measurements.

Gemini used 6,099 input and 408 output tokens. The evidence contains no bill, so any dollar cost is an external-price inference. Ollama had zero marginal API fee, but electricity, hardware, depreciation, and maintenance were not measured and are not free.

## Recommendation

**Measured fact:** Gemini and 26B both passed 12/12 warm quality trials, but Gemini's warm mean was about 20 times faster (`12.883 / 0.636`). 26B was faster and more accurate than 12B on this host; 12B failed the named regression.

**Inference:** retain Gemini Flash-Lite as the default and consider 26B only as an optional privacy/offline mode. The corpus and host sample are small, so this is not a universal hardware or quality claim. No default provider, model, or STT setting is changed by this recommendation.
