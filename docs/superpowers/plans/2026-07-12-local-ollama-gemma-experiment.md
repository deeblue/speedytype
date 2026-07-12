# Local Ollama Gemma Experiment Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an optional local Ollama polishing provider and compare `gemma4:12b` and `gemma4:26b` against online `gemini-3.1-flash-lite` while retaining `whisper-1` STT.

**Architecture:** Add a native Ollama `/api/chat` adapter behind the existing provider-neutral `LlmResult` interface. Extend configuration only for Ollama connection settings, then use a resumable benchmark script to run identical quality cases and cold/warm performance trials serially across all three candidates.

**Tech Stack:** Python 3.13, `requests`, Ollama native HTTP API, pytest, JSONL, existing SpeedyType prompt and LLM abstractions.

## Global Constraints

- `whisper-1` remains the only production STT model in this experiment.
- `gemini-3.1-flash-lite` remains the default online polishing model.
- No automatic provider fallback is allowed during comparison runs.
- `LLM_PROVIDER=ollama` is opt-in through `.env`; no Settings UI selector is added.
- Benchmark candidates run serially and each quality case runs at least three times.
- Cold-start and warm-start measurements remain separate.
- Raw benchmark results are appended incrementally to JSONL.
- No default provider change is made from benchmark results without a separate user decision.

---

### Task 1: Provider-Conditional Configuration

**Files:**
- Modify: `speedytype/config.py`
- Modify: `.env.example`
- Test: `tests/test_config.py`

**Interfaces:**
- Produces: `AppConfig.ollama_base_url: str`
- Produces: `AppConfig.ollama_keep_alive: str`
- Changes: `load_config()` requires `OPENAI_API_KEY` always, but requires a polishing-provider key only for `gemini` or `minimax`.

- [ ] **Step 1: Write failing tests for Ollama configuration and conditional keys**

Add tests that load this environment:

```python
env_file.write_text(
    "OPENAI_API_KEY=sk-test\n"
    "LLM_PROVIDER=ollama\n"
    "LLM_MODEL=gemma4:12b\n"
    "OLLAMA_BASE_URL=http://localhost:11435\n"
    "OLLAMA_KEEP_ALIVE=15m\n",
    encoding="utf-8",
)
config = load_config(env_file, settings_path=tmp_path / "settings.json")
assert config.llm_provider == "ollama"
assert config.llm_model == "gemma4:12b"
assert config.ollama_base_url == "http://localhost:11435"
assert config.ollama_keep_alive == "15m"
```

Also assert missing `OPENAI_API_KEY` still raises, missing Gemini is accepted for Ollama, and missing Gemini still raises for `LLM_PROVIDER=gemini`.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_config.py -q`

Expected: failures because Ollama fields do not exist and Gemini is unconditionally required.

- [ ] **Step 3: Implement minimal conditional validation**

Add immutable fields with defaults:

```python
ollama_base_url: str = "http://127.0.0.1:11434"
ollama_keep_alive: str = "10m"
```

Resolve `LLM_PROVIDER` before validation. Build required keys as `OPENAI_API_KEY` plus `GEMINI_API_KEY` only for Gemini and `MINIMAX_API_KEY` only for MiniMax. Parse `OLLAMA_BASE_URL` with trailing `/` removed and reject an empty value by reverting to the default.

- [ ] **Step 4: Document environment settings**

Append to `.env.example`:

```env
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_KEEP_ALIVE=10m
```

Keep `LLM_PROVIDER=gemini` and `LLM_MODEL=gemini-3.1-flash-lite` unchanged.

- [ ] **Step 5: Verify GREEN**

Run: `python -m pytest tests/test_config.py -q`

Expected: all configuration tests pass.

- [ ] **Step 6: Commit**

```powershell
git add speedytype/config.py tests/test_config.py .env.example
git commit -m "feat: configure optional Ollama polishing"
```

### Task 2: Native Ollama Polishing Adapter

**Files:**
- Modify: `speedytype/llm.py`
- Create: `tests/test_ollama_llm.py`

**Interfaces:**
- Produces: `parse_ollama_text(payload: dict[str, Any]) -> str`
- Produces: `call_ollama_polisher(text: str, config: AppConfig, *, model: str, timeout_seconds: int = 120) -> LlmResult`
- Consumes: `AppConfig.ollama_base_url`, `AppConfig.ollama_keep_alive`, `build_system_prompt(config)`.

- [ ] **Step 1: Write failing parser and dispatch tests**

Use a representative native response:

```python
payload = {
    "model": "gemma4:12b",
    "message": {"role": "assistant", "content": "整理後文字。"},
    "done": True,
    "total_duration": 2_000_000_000,
    "load_duration": 500_000_000,
    "prompt_eval_count": 120,
    "prompt_eval_duration": 300_000_000,
    "eval_count": 20,
    "eval_duration": 1_000_000_000,
}
```

Assert trimmed text, token mapping (`120`, `20`, `140`), provider/model values, request URL, `stream=False`, `think=False`, temperature `0.1`, `num_predict=512`, and configured `keep_alive`. Add empty-content and malformed-message tests that require actionable `RuntimeError` messages.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_ollama_llm.py -q`

Expected: import failure because Ollama functions do not exist.

- [ ] **Step 3: Implement parser, usage mapping, and adapter**

Send this request shape:

```python
body = {
    "model": model,
    "messages": [
        {"role": "system", "content": build_system_prompt(config)},
        {"role": "user", "content": text},
    ],
    "stream": False,
    "think": False,
    "keep_alive": config.ollama_keep_alive,
    "options": {"temperature": 0.1, "num_predict": 512},
}
```

POST to `f"{config.ollama_base_url}/api/chat"`. Map `prompt_eval_count` and `eval_count` into `LlmUsage`; preserve the full native response in `raw_response`. Convert connection errors and timeouts to messages naming Ollama URL/model. Do not retry connection failures and do not call any online provider.

- [ ] **Step 4: Add provider dispatch**

Extend `call_llm_polisher()`:

```python
if provider == "ollama":
    return call_ollama_polisher(text, config, model=config.llm_model)
```

- [ ] **Step 5: Verify focused and provider regression tests**

Run: `python -m pytest tests/test_ollama_llm.py tests/test_config.py tests/test_hybrid_integration.py -q`

Expected: all pass; existing pipeline mocks remain compatible.

- [ ] **Step 6: Commit**

```powershell
git add speedytype/llm.py tests/test_ollama_llm.py
git commit -m "feat: add native Ollama polisher"
```

### Task 3: Resumable Three-Model Benchmark

**Files:**
- Create: `scripts/run_local_llm_benchmark.py`
- Create: `tests/test_local_llm_benchmark.py`

**Interfaces:**
- Produces: `BenchmarkCase(name: str, category: str, text: str)`
- Produces: `quality_flags(case: BenchmarkCase, output: str) -> dict[str, bool]`
- Produces: `run_candidate(config, candidate, case, mode, repetition) -> dict[str, Any]`
- Writes: `local_llm_benchmark_results.jsonl`

- [ ] **Step 1: Write failing benchmark-unit tests**

Test the three Phase 2 inputs, the repeated-number case, candidate list, quality flags, nanosecond-to-second duration conversion, output-token throughput, and resume identity `(provider, model, case, mode, repetition)`. Assert failures are retained with `ok=false` and semantic quality is absent rather than marked false.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/test_local_llm_benchmark.py -q`

Expected: missing module failure.

- [ ] **Step 3: Implement cases and quality checks**

Reuse the Phase 2 short/medium/long transcript strings and quality rules without weakening them. Add:

```python
BenchmarkCase(
    "numbers_repeated_english",
    "number_regression",
    "123測試測試 123測試測試 123 test 123 test",
)
```

Require the cleaned output to retain `123` and one meaningful `test`/`測試` form without extra explanatory text.

- [ ] **Step 4: Implement serial, incremental execution**

Candidates are fixed to:

```python
(
    {"provider": "gemini", "model": "gemini-3.1-flash-lite", "thinking": "minimal"},
    {"provider": "ollama", "model": "gemma4:12b"},
    {"provider": "ollama", "model": "gemma4:26b"},
)
```

For each local model, call `ollama stop <model>` before its single cold trial, then run three warm repetitions with `OLLAMA_KEEP_ALIVE`. Append and flush one JSON object per result. Skip already completed identities unless `--rerun` is supplied. Never run candidates concurrently.

- [ ] **Step 5: Record native metrics and host observations**

For Ollama records extract `load_duration`, `prompt_eval_duration`, `eval_duration`, prompt/output counts, and calculated output tokens/second. Query `ollama ps` after successful local calls and store its text as diagnostic evidence. Online records retain existing Gemini usage and call timing.

- [ ] **Step 6: Verify GREEN**

Run: `python -m pytest tests/test_local_llm_benchmark.py -q`

Expected: all benchmark unit tests pass without calling external services.

- [ ] **Step 7: Commit**

```powershell
git add scripts/run_local_llm_benchmark.py tests/test_local_llm_benchmark.py
git commit -m "test: add local Gemma comparison benchmark"
```

### Task 4: Offline Verification and Live Benchmark

**Files:**
- Create during execution: `local_llm_benchmark_results.jsonl`

**Interfaces:**
- Consumes: `scripts/run_local_llm_benchmark.py`
- Produces: raw evidence for all three candidates.

- [ ] **Step 1: Run the full offline test suite**

Run: `$env:QT_QPA_PLATFORM='offscreen'; python -m pytest -q`

Expected: all tests pass before live model calls begin.

- [ ] **Step 2: Verify Ollama prerequisites**

Run:

```powershell
ollama list
ollama show gemma4:12b
ollama show gemma4:26b
```

Expected: both exact model tags exist and Ollama accepts local commands.

- [ ] **Step 3: Execute the benchmark**

Run:

```powershell
python scripts/run_local_llm_benchmark.py --env .env --output local_llm_benchmark_results.jsonl --repetitions 3
```

Expected: one cold trial and at least three warm quality repetitions per local candidate, plus at least three Gemini repetitions per quality case. Any failures are present as raw JSONL records, not silently retried under another provider.

- [ ] **Step 4: Audit completeness**

Run the script's `--summarize-only` mode and verify every candidate/case has the requested valid or explicitly failed records. Rerun only missing identities using the default resume behavior.

- [ ] **Step 5: Commit raw evidence**

```powershell
git add local_llm_benchmark_results.jsonl
git commit -m "test: record local Gemma benchmark evidence"
```

### Task 5: Comparison Report and Final Verification

**Files:**
- Create: `LOCAL_LLM_EXPERIMENT_REPORT.md`
- Modify: `POC_REPORT.md`

**Interfaces:**
- Consumes: `local_llm_benchmark_results.jsonl`
- Produces: adoption recommendation without changing defaults.

- [ ] **Step 1: Generate candidate summaries**

Report per candidate:

- Successful calls / attempted calls.
- Quality pass count and per-dimension failures.
- Repeated-number regression result.
- Cold call and model load seconds.
- Warm mean, median, minimum, maximum, and p95 call seconds.
- Mean output tokens/second.
- Memory/processor observations from `ollama ps` diagnostics.
- Online estimated cost versus local zero marginal API cost, without claiming electricity is free.

- [ ] **Step 2: Write the evidence-based recommendation**

Create `LOCAL_LLM_EXPERIMENT_REPORT.md` with raw record references and explicitly distinguish measured facts from inference. Recommend one of: remain online, use 12B locally, use 26B locally, or expose local mode as optional. Do not edit `.env`, `DEFAULT_GEMINI_MODEL`, or the default `llm_provider`.

- [ ] **Step 3: Link the report from the POC report**

Add a concise experiment summary and link to `LOCAL_LLM_EXPERIMENT_REPORT.md` in `POC_REPORT.md`, including that STT remained `whisper-1` throughout.

- [ ] **Step 4: Run fresh verification**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q
git diff --check
git status --short
```

Expected: all tests pass, no whitespace errors, and only intended report/result files are pending.

- [ ] **Step 5: Commit report**

```powershell
git add LOCAL_LLM_EXPERIMENT_REPORT.md POC_REPORT.md
git commit -m "docs: report local Gemma model comparison"
```

