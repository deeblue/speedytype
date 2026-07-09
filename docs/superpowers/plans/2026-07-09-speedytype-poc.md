# SpeedyType POC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and verify a Windows Python POC for hold-to-record voice input, Whisper transcription, Gemini Flash cleanup, clipboard write, simulated paste, and latency logging.

**Architecture:** Keep the core pipeline testable by splitting config loading, API parsing/calls, recording, paste, and latency logging into small modules. The interactive hotkey loop calls the same pipeline used by integration commands, so batch tests and real use exercise shared code.

**Tech Stack:** Python 3, requests, python-dotenv, sounddevice, soundfile, pyperclip, keyboard, pytest.

## Global Constraints

- Language: Python 3.
- Hotkey default: F9.
- Recording format: 16kHz, mono, WAV.
- Whisper endpoint: `https://api.openai.com/v1/audio/transcriptions`, model `whisper-1`, with prompt from config.
- Gemini endpoint: `generateContent`, Flash model discovered from Google API when possible, defaulting to current documented stable `gemini-3.5-flash`.
- JSON parsing must use Python `json` / structured dict access, never regular expressions.
- API non-200 errors must print status code and full response body.
- Clipboard write and paste must include at least 100ms delay before Ctrl+V.
- Latency log: `speedytype_latency_log.csv` with timestamp, recording length, Whisper seconds, Gemini seconds, paste seconds, total tail latency.
- No real API keys in committed files.

---

### Task 1: Testable Core Interfaces

**Files:**
- Create: `tests/test_parsers.py`
- Create: `tests/test_config.py`
- Create: `speedytype/__init__.py`
- Create: `speedytype/config.py`
- Create: `speedytype/api.py`

**Interfaces:**
- Produces: `load_config(path: str = ".env") -> AppConfig`
- Produces: `parse_whisper_text(payload: dict) -> str`
- Produces: `parse_gemini_text(payload: dict) -> str`
- Produces: `ApiResponseFormatError`

- [x] **Step 1: Write failing parser and config tests.**
- [x] **Step 2: Run tests and confirm import failures.**
- [x] **Step 3: Implement minimal config and parser code.**
- [x] **Step 4: Re-run tests and confirm pass.**

### Task 2: Pipeline, Recording, Paste, and Logging

**Files:**
- Create: `speedytype/audio.py`
- Create: `speedytype/clipboard.py`
- Create: `speedytype/latency.py`
- Create: `speedytype/pipeline.py`
- Create: `speedytype/cli.py`
- Create: `speedytype/__main__.py`
- Create: `.env.example`
- Create: `requirements.txt`

**Interfaces:**
- Consumes: `AppConfig`, `transcribe_audio`, `polish_text`
- Produces: `python -m speedytype run-once <wav>`
- Produces: `python -m speedytype listen`
- Produces: `python -m speedytype diagnose-config`

- [x] **Step 1: Add CLI and pipeline tests where external systems can be mocked.**
- [x] **Step 2: Implement file-based pipeline and latency CSV writer.**
- [x] **Step 3: Implement hold-to-record F9 loop using `keyboard` and callback recording using `sounddevice`/`soundfile`.**
- [x] **Step 4: Implement clipboard paste with clear fallback message on paste failure uncertainty.**

### Task 3: Verification and Report

**Files:**
- Create: `POC_REPORT.md`
- Create or append: `speedytype_latency_log.csv`

**Interfaces:**
- Consumes: CLI commands.
- Produces: evidence for unit tests, config failure test, Gemini model lookup, and attempted integration/manual tests.

- [x] **Step 1: Run unit tests and capture output.**
- [x] **Step 2: Run config missing-key diagnostic and capture output.**
- [x] **Step 3: Attempt real API and latency benchmark only if keys/audio/device conditions are present.**
- [x] **Step 4: Record blocked or untested items explicitly with reasons and no fabricated metrics.**
