# Local Ollama Gemma Experiment Design

Date: 2026-07-12

## Goal

Evaluate whether either locally installed `gemma4:12b` or `gemma4:26b` can replace the online Gemini polishing step without reducing transcript quality or making post-recording latency unacceptable. Speech-to-text remains OpenAI `whisper-1`; this experiment does not attempt local STT.

## Scope

- Add Ollama as an optional LLM polishing provider.
- Keep `gemini-3.1-flash-lite` as the production default and online benchmark baseline.
- Compare the baseline with local `gemma4:12b` and `gemma4:26b` using identical prompts and inputs.
- Record quality, cold-start latency, warm latency, generation throughput, token counts, model load time, and memory observations.
- Store raw benchmark records in JSONL and summarize the evidence in Markdown.

The experiment does not change hotkeys, recording, clipboard behavior, hybrid transcription, platform backends, or the default LLM provider.

## Installed Models and Host

The target Windows host currently has:

- `gemma4:12b`, 11.9B parameters, `Q4_K_M`, approximately 7.6 GB.
- `gemma4:26b`, 25.8B parameters, `Q4_K_M`, approximately 17 GB.
- Intel Core Ultra 9 285H, approximately 64 GB system RAM, and Intel Arc 140T graphics.

Model capacity does not establish usable latency. The benchmark must measure actual cold and warm behavior on this host.

## Architecture

### Provider Integration

Add an `ollama` branch to the existing provider-neutral `call_llm_polisher()` dispatch. The adapter calls Ollama's native `POST /api/chat` endpoint rather than its OpenAI-compatible endpoint because the native response exposes model loading, prompt evaluation, generation timing, and token counts.

The adapter uses the existing system prompt and sends the raw Whisper transcript as the user message. It returns the existing `LlmResult` type so `pipeline.py`, quasi-streaming, latency logging, Gemini polishing, and paste behavior remain unchanged.

The adapter uses deterministic, low-temperature generation suitable for cleanup rather than creative writing. Thinking output must not appear in the pasted transcript. Any model-specific thinking control will be explicit and recorded in benchmark configuration.

### Configuration

The following environment configuration selects local polishing:

```env
LLM_PROVIDER=ollama
LLM_MODEL=gemma4:12b
OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_KEEP_ALIVE=10m
```

`OLLAMA_BASE_URL` and `OLLAMA_KEEP_ALIVE` receive safe defaults. OpenAI remains required because `whisper-1` is unchanged. Gemini is required only when the selected polishing provider is Gemini; MiniMax remains required only for MiniMax. This removes the current unconditional Gemini-key requirement when running a local polisher without weakening STT configuration validation.

No Settings UI model selector is added during the experiment. Selection remains explicit in `.env`, which prevents an experimental provider from appearing production-ready.

### Error Handling

The Ollama adapter reports actionable errors for:

- Ollama not running or unreachable.
- Requested model not installed.
- Request timeout.
- Non-success HTTP response.
- Missing or empty assistant output.
- Unexpected response structure.

There is no automatic fallback to Gemini during benchmark runs. Silent fallback would mix providers and invalidate latency and quality results. The normal pipeline fails before clipboard paste when local polishing fails.

## Benchmark Design

### Candidates

1. Online baseline: `gemini-3.1-flash-lite`, minimal thinking.
2. Local candidate: `gemma4:12b`.
3. Local candidate: `gemma4:26b`.

All candidates receive the same production system prompt and unmodified input transcript.

### Inputs

- The existing Phase 2 nine-case polishing set, covering short, medium, and long content.
- Existing real transcript fixtures representing short, medium, and long recordings.
- The named repeated-number regression input containing forms of `123測試測試` and `123 test`.

Each candidate runs each quality input at least three times. API failures are recorded separately and excluded from semantic pass rates, while reliability rates retain the failed calls.

### Quality Dimensions

- Filler removal.
- Correct handling of user self-correction.
- Logical paragraph and Markdown list formatting.
- Technical-term preservation.
- Number and identifier preservation.
- No added greeting, explanation, or unsupported content.

Results must include per-case failures rather than only an aggregate score. Local adoption requires no regression in the named repeated-number case and no material decline from the Gemini baseline in any quality dimension.

### Performance Measurements

Cold-start and warm performance are separate experiments:

- Cold start: unload the candidate, then time its first request including model loading.
- Warm start: keep the model resident with `keep_alive`, then run repeated identical-workload requests.

Record:

- End-to-end LLM call seconds measured by the application.
- Ollama `load_duration`, `prompt_eval_duration`, and `eval_duration`.
- Prompt and output token counts.
- Output tokens per second derived from Ollama counters.
- Process/model memory observations before and during the run when available.
- Success, timeout, and malformed/empty-output rates.

The benchmark runs candidates serially so two resident models do not compete for memory. Raw results are written incrementally to JSONL so an interrupted 26B run does not lose completed evidence.

## Tests

Automated tests cover:

- Ollama response parsing and usage/timing mapping.
- Provider dispatch for `LLM_PROVIDER=ollama`.
- Configuration defaults and provider-conditional API-key validation.
- Unreachable service, missing model, timeout, non-success response, and empty output.
- Preservation of existing Gemini, OpenAI, and MiniMax dispatch behavior.
- The named repeated-number prompt regression remains part of the quality benchmark.

The full existing pytest suite must pass before paid or long-running comparisons begin.

## Decision Output

The report ranks the three candidates separately for quality, warm latency, cold latency, throughput, reliability, and operating cost. It may recommend:

- Keep Gemini online.
- Use `gemma4:12b` locally.
- Use `gemma4:26b` locally.
- Keep local models as an optional privacy/offline mode rather than the default.

No recommendation automatically changes `LLM_PROVIDER` or the production default. A default change requires a separate user decision after reviewing raw evidence.

