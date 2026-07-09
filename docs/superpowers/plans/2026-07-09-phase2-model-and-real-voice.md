# Phase 2 Model and Real Voice Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Compare low-latency LLM polishing providers with corrected retry timing, then add guided real-voice recording and validation tooling.

**Architecture:** Add provider-neutral LLM calls beside the existing Gemini implementation. Experiments write JSONL/CSV evidence and reports; the production pipeline reads default provider/model settings from `.env`. Real-voice commands reuse the existing recorder, transcriber, selected LLM provider, and latency logger.

**Tech Stack:** Python 3, requests, sounddevice/soundfile, pyperclip/keyboard, pytest, pywinauto, MiniMax/OpenAI/Gemini HTTP APIs.

## Global Constraints

- Do not fabricate API results, latency, quality, or cost numbers.
- Anthropic is skipped because there is no API billing plan.
- Backoff wait must be logged separately from pure API call time.
- Logs must include `llm_provider`, `llm_model`, `llm_call_seconds`, and `retry_wait_seconds`.
- 真人語音結果不得編造; only tooling and fake-WAV flow tests can be automated before the user records.

---

### Task 1: Provider-Neutral LLM Layer

**Files:**
- Create: `speedytype/llm.py`
- Modify: `speedytype/config.py`
- Test: `tests/test_llm_retry.py`

**Interfaces:**
- Produces: `LlmConfig`, `LlmResult`, `call_llm_polisher(text, config)`
- Produces: retry timing that separates API seconds from sleep seconds.

- [x] Write retry timing tests.
- [x] Implement provider-neutral result types.
- [x] Implement Gemini/OpenAI/MiniMax calls.
- [x] Re-run tests.

### Task 2: Phase 2 Experiments

**Files:**
- Create: `scripts/phase2_probe_models.py`
- Create: `scripts/phase2_run_llm_experiment.py`
- Modify: `scripts/generate_test_audio.py`
- Create: `PHASE2_MODEL_REPORT.md`

**Interfaces:**
- Produces: `phase2_probe_results.json`
- Produces: `phase2_llm_results.jsonl`
- Produces: latency/quality/cost report with final setting.

- [x] Probe model/parameter acceptance with real API calls.
- [x] Run 3 repetitions per transcript per candidate setting.
- [x] Record latency, output, usage, quality marks, and cost estimates.
- [x] Update `.env.example` and `.env` default LLM setting.

### Task 3: Real Voice Tooling

**Files:**
- Create: `real_voice_script.md`
- Modify: `speedytype/cli.py`
- Create: `speedytype/real_voice.py`
- Create: `REAL_VOICE_REPORT.md`
- Test: `tests/test_real_voice.py`

**Interfaces:**
- Produces: `python -m speedytype guided-recording --script real_voice_script.md`
- Produces: `python -m speedytype validate-real-voice --dir real_voice`

- [x] Create reading script.
- [x] Implement guided recording command.
- [x] Implement validation/report command.
- [x] Add fake-WAV flow tests.
- [x] Re-run tests.
