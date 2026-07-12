# Final Review Fixes Report

Status: DONE_WITH_CONCERNS
Date: 2026-07-12 Asia/Taipei

## TDD evidence

- RED: `python -m pytest tests/test_local_llm_benchmark.py tests/test_config.py tests/test_ollama_llm.py -q` -> 12 failed, 31 passed in 1.34s. Failures covered all-candidate cold isolation, trailing-fragment repair, non-final corruption rejection, rerun recreation, snapshot contamination, provider normalization, early unsupported-provider rejection, and mixed-case dispatch.
- GREEN: same focused command -> 43 passed in 1.12s.
- Full pre-benchmark verification: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q` -> 171 passed in 3.67s. `git diff --check` passed.
- Code/tests commit: `1a03c31 fix: harden local benchmark isolation and resume`.

## Live evidence

- Prerequisites: exact `gemma4:12b` and `gemma4:26b` tags present; both `ollama show` commands exited 0.
- Output was truncated, then the documented default command ran: `python scripts/run_local_llm_benchmark.py --env .env --output local_llm_benchmark_results.jsonl --repetitions 3`.
- Live timing: 571.948 seconds, exit 0.
- Summarize-only: 38 records, 38 expected, 38 unique; parse errors 0, duplicates 0, missing 0, unexpected 0; complete=true.
- Isolation proof: every local record captured `ollama ps`; 13/13 12B snapshots contained only 12B, 13/13 26B snapshots contained only 26B, and 0 snapshots contained both candidates.
- Evidence SHA-256: `B8466AD25190A800ED4748E617BB38460A0C063004C01188DD9AF70C1AC02019`.

## Outcome

- Gemini: 12/12 quality, 0.636s warm mean.
- Gemma 12B: 9/12 warm quality, 27.255s warm mean, 38.980s cold; repeated-number 0/3.
- Gemma 26B: 12/12 warm quality, 12.883s warm mean, 37.355s cold; repeated-number 3/3.
- Recommendation: retain Gemini default; consider 26B only as optional privacy/offline mode. No default or STT change.

Concerns: small deterministic corpus, one Windows CPU-only host, one cold trial per local model, and no measured electricity/hardware cost. These limit generalization but do not affect completeness or isolation of this run.

Final verification concern: the pre-benchmark full suite passed 171/171. After the live run, a fresh full-suite attempt passed 166 tests but five real Windows clipboard tests failed because another process held the OS clipboard (`OpenClipboard: Access is denied`). An isolated retry reproduced the same external lock (1 passed, 5 failed). Focused benchmark/config/provider tests remain 43/43 green; benchmark completeness, isolation, hash, and `git diff --check` remain verified.
