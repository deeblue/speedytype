# Full-file FLAC Long-recording Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship durable WAV capture, validated lossless full-file FLAC upload, safe short-WAV fallback, recovery discovery, and one enforced 25-minute recording ceiling.

**Architecture:** Capture and recovery metadata are independent of upload preparation. `flac_upload.py` returns a context-managed selected artifact only after format, PCM-conservation, duration, and actual-byte checks; `pipeline.py` consumes that selection through the existing complete-file JSON API. No segmented, timestamped, or lossy path is enabled.

**Tech Stack:** Python 3.13, sounddevice, soundfile/libsndfile, imageio-ffmpeg, NumPy, PyQt6, pytest.

## Global Constraints

- Capture is mono PCM16 WAV at 16 kHz and must drain queued samples on stop.
- `MAX_MAX_RECORD_SECONDS = 1500.0`; default remains `60.0`.
- FLAC and direct-WAV admission require actual bytes `< 23 * 1024 * 1024`.
- Production transcription is one `whisper-1` request with `response_format=json`; no timestamp granularities.
- FLAC validation requires readable PCM16 semantics, exact frame equality, and decoded PCM SHA-256 equality.
- Direct WAV fallback is allowed only after FLAC preparation failure and only when WAV itself passes duration/size admission.
- Every failure retains WAV; recovery discovery never submits an API request.
- Do not reuse or add Opus, MP3, segmented transcription, `verbose_json`, or word merging.

---

### Task 1: Enforce the 25-minute setting in model, config, and UI

**Files:**
- Modify: `speedytype/settings.py`
- Modify: `speedytype/config.py`
- Modify: `speedytype/settings_dialog.py`
- Modify: `tests/test_settings.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_settings_dialog.py`

**Interfaces:**
- Produces: `MAX_MAX_RECORD_SECONDS = 1500.0` and `AppSettings.load_warnings` entry for clamped persisted values.
- Consumed by: Settings slider and `load_config()` runtime bound.

- [x] **Step 1: Write failing setting/config/UI tests**

Add tests asserting an on-disk `max_record_seconds: 1800` loads as `1500.0` with a visible warning, `1500.0` round-trips, direct invalid constructor save is rejected, `load_config()` returns no value above 1500, and the slider maximum/label are `1500` / `25 分鐘`.

- [x] **Step 2: Run the focused tests and confirm RED**

Run: `python -m pytest tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py -q`

Expected: failures showing the current `540.0` maximum and absent clamp warning.

- [x] **Step 3: Implement exact validation**

Use one helper in `settings.py`:

```python
def _validated_record_seconds(raw: object) -> tuple[float, tuple[str, ...]]:
    value = float(raw)
    if not math.isfinite(value) or value < MIN_MAX_RECORD_SECONDS:
        raise ValueError("max_record_seconds must be finite and at least 60")
    if value > MAX_MAX_RECORD_SECONDS:
        return MAX_MAX_RECORD_SECONDS, ("最大錄音時間已限制為 25 分鐘。",)
    return value, ()
```

Merge this warning with budget warnings, reject invalid direct saves, and retain the existing 60-second default. The dialog continues to derive its slider maximum from the constant.

- [x] **Step 4: Run focused tests and confirm GREEN**

Run the Step 2 command. Expected: all pass.

- [x] **Step 5: Commit**

```powershell
git add speedytype/settings.py speedytype/config.py speedytype/settings_dialog.py tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py
git commit -m "feat: enforce 25 minute recording limit"
```

---

### Task 2: Add durable sample-indexed WAV capture and recovery metadata

**Files:**
- Create: `speedytype/capture_writer.py`
- Create: `speedytype/recording_recovery.py`
- Modify: `speedytype/paths.py`
- Modify: `speedytype/audio.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/cli.py`
- Create: `tests/test_capture_writer.py`
- Create: `tests/test_recording_recovery.py`
- Modify: `tests/test_audio_recording.py`
- Modify: `tests/test_daemon_recovery.py`

**Interfaces:**
- Produces: `SampleIndexedWavWriter.submit(block)`, `.finish() -> CaptureWriteStats`, `create_recording_path() -> Path`, `mark_recording(path, state, error_category="")`, and `discover_recoverable_recordings() -> tuple[RecoveryRecord, ...]`.
- Consumed by: recorder, daemon, CLI, and Task 4 pipeline.

- [x] **Step 1: Write failing writer tests**

Cover exact submitted/written frames, ordered blocks, queue-full abort, background write error, `finish()` drain, and a synthetic 28.8-million-frame stress with zero loss. Tests must use generated arrays and temporary directories, not microphone input.

- [x] **Step 2: Confirm writer tests RED**

Run: `python -m pytest tests/test_capture_writer.py tests/test_audio_recording.py -q`

Expected: import/interface failures because the writer does not exist.

- [x] **Step 3: Implement the bounded writer and recordings path**

`SampleIndexedWavWriter` owns a bounded `queue.Queue`, one writer thread, an expected next-frame index, and a terminal error. `submit()` copies the block and assigns its frame range; `finish()` enqueues a sentinel, joins, flushes/closes, and raises any stored error. Add:

```python
def default_recordings_dir() -> Path:
    return app_data_dir() / "recordings"
```

Change `temp_wav_path()` to create owned WAV paths there and change `Recorder.record_until_stop()` to route callback blocks through the writer, then drain on exit.

- [x] **Step 4: Write recovery-state tests and confirm RED**

Test atomic JSON sidecars, allowed state transitions, sanitized error categories, discovery of `capturing`, `captured`, `encoding`, `ready`, `processing`, and `failed-retained`, exclusion of `completed`, corrupt-sidecar reporting, and proof that discovery never imports/calls the API module.

- [x] **Step 5: Implement recovery metadata and capture transitions**

Use `<wav>.speedytype.json`, atomic temporary write/replace, and these exact states:

```python
RECOVERABLE_STATES = frozenset({
    "capturing", "captured", "encoding", "ready", "processing", "failed-retained"
})
```

Create the `capturing` sidecar with the path, UUID, timestamp, and state; mark `captured` only after writer drain. Daemon/CLI recording exceptions mark `failed-retained` and report the WAV path without deleting it.

- [x] **Step 6: Run Task 2 tests and confirm GREEN**

Run: `python -m pytest tests/test_capture_writer.py tests/test_audio_recording.py tests/test_recording_recovery.py tests/test_daemon_recovery.py -q`

Expected: all pass.

- [x] **Step 7: Commit**

```powershell
git add speedytype/capture_writer.py speedytype/recording_recovery.py speedytype/paths.py speedytype/audio.py speedytype/daemon.py speedytype/cli.py tests/test_capture_writer.py tests/test_recording_recovery.py tests/test_audio_recording.py tests/test_daemon_recovery.py
git commit -m "feat: preserve durable WAV recordings"
```

---

### Task 3: Build lossless FLAC preparation and admission

**Files:**
- Create: `speedytype/flac_upload.py`
- Create: `tests/test_flac_upload.py`

**Interfaces:**
- Produces: `prepare_upload(wav_path, *, max_bytes=23*1024*1024, max_seconds=1500.0) -> AbstractContextManager[PreparedUpload]`.
- `PreparedUpload` fields: `path`, `container`, `source_wav`, `source_bytes`, `upload_bytes`, `duration_seconds`, `encoding_seconds`, `fallback_used`, `fallback_reason`, `validation`.
- Raises: `UploadPreparationError(category, preserved_wav)` when neither FLAC nor WAV is admissible.

- [ ] **Step 1: Write failing FLAC tests**

Cover real lossless encode/decode, atomic promotion, cleanup of owned partial files, readable mono/16-kHz/PCM16 validation, frame mismatch, PCM mismatch, exact `<23 MiB` boundary, 1500-second inclusive boundary, 1500.001 rejection, and non-empty regular-file checks.

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_flac_upload.py -q`

Expected: import/interface failures.

- [ ] **Step 3: Implement three-layer validation**

Encode to a unique `.partial.flac`, run ffmpeg with `-c:a flac -sample_fmt s16 -ac 1 -ar 16000 -map_metadata -1`, close it, validate through `soundfile`, calculate blockwise PCM SHA-256 for source and decoded FLAC, then `replace()` to the final owned artifact. Admission uses strict `< max_bytes`.

- [ ] **Step 4: Add failing fallback tests**

Inject encoder/validation failures. Assert an admissible WAV returns `container="wav"` and `fallback_used=True`; an oversize or over-duration WAV raises `UploadPreparationError`; no failure deletes the WAV; successful context exit deletes only the FLAC.

- [ ] **Step 5: Implement fallback selection and cleanup**

Catch only classified FLAC preparation errors. Check the WAV's actual byte count and duration against the same guards before selecting it. Keep source WAV outside every cleanup list.

- [ ] **Step 6: Run Task 3 tests and confirm GREEN**

Run: `python -m pytest tests/test_flac_upload.py -q`

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add speedytype/flac_upload.py tests/test_flac_upload.py
git commit -m "feat: prepare validated lossless FLAC uploads"
```

---

### Task 4: Integrate complete-file upload, diagnostics, and startup recovery

**Files:**
- Modify: `speedytype/pipeline.py`
- Modify: `speedytype/latency.py`
- Modify: `speedytype/daemon.py`
- Modify: `speedytype/cli.py`
- Modify: `speedytype/api.py`
- Modify: `tests/test_pipeline_usage.py`
- Modify: `tests/test_usage_stats.py`
- Modify: `tests/test_daemon_recovery.py`
- Modify: `tests/test_parsers.py`

**Interfaces:**
- Consumes: `prepare_upload()` and recovery state functions.
- Produces: latency fields `stt_upload_container`, `stt_upload_bytes`, `stt_encoding_seconds`, `stt_wav_fallback_used`, and `stt_wav_fallback_reason`.

- [ ] **Step 1: Write failing pipeline request tests**

Assert normal processing transcribes the selected FLAC, fallback processing transcribes WAV, both calls use `whisper-1` through the normal JSON `transcribe_audio()` path, `.flac` MIME is `audio/flac`, and no production call requests verbose/timestamps. Assert short recordings skip before FLAC preparation.

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_pipeline_usage.py tests/test_parsers.py -q`

Expected: selected-upload and diagnostic assertions fail.

- [ ] **Step 3: Integrate the context-managed upload**

In `process_wav()`, mark `encoding`, enter `prepare_upload(audio_path)`, mark `ready`, then `processing`, call `transcribe_audio(prepared.path, config, model=stt_model)`, and write upload diagnostics. Mark `failed-retained` on preparation/transcription/polish exceptions, empty provider text, or a requested paste that returns `paste_ok=False`. Mark `completed` only for a successful requested paste, an intentional `do_paste=False` completion, or the existing local `<0.1 s` no-API skip. Recovery functions are no-ops for arbitrary WAVs outside SpeedyType's owned recordings directory.

- [ ] **Step 4: Extend latency CSV compatibility**

Append the five new fields to `LATENCY_FIELDS`; defaults preserve old callers and usage calculation. Update tests proving old CSVs remain readable and fallback uploaded seconds/cost remain accurate.

- [ ] **Step 5: Add startup discovery tests and confirm RED**

Construct recoverable records before `run_daemon()`. Assert one sanitized startup summary is printed/shown, completed records are absent, and neither `transcribe_audio` nor `process_wav` is called.

- [ ] **Step 6: Implement non-submitting recovery notification**

Discover after Qt/tray initialization. Print count and preserved paths through `safe_print`; use tray notification copy that says recordings require manual review. Do not add retry/resume buttons or provider calls.

- [ ] **Step 7: Run integration tests and confirm GREEN**

Run: `python -m pytest tests/test_pipeline_usage.py tests/test_usage_stats.py tests/test_daemon_recovery.py tests/test_parsers.py -q`

Expected: all pass.

- [ ] **Step 8: Commit**

```powershell
git add speedytype/pipeline.py speedytype/latency.py speedytype/daemon.py speedytype/cli.py speedytype/api.py tests/test_pipeline_usage.py tests/test_usage_stats.py tests/test_daemon_recovery.py tests/test_parsers.py
git commit -m "feat: use complete-file FLAC transcription path"
```

---

### Task 5: Remove obsolete hybrid activation, document, and verify release gates

**Files:**
- Modify: `speedytype/config.py`
- Modify: `speedytype/daemon.py`
- Modify: `release/README.md`
- Modify: `MAC_SETUP.md`
- Modify: `KNOWN_LIMITATIONS.md`
- Modify: `POC_REPORT.md`
- Modify: `tests/test_release_docs.py`

**Interfaces:**
- Produces: one documented production path and an explicit real-device checklist.

- [ ] **Step 1: Write failing path-selection/documentation tests**

Assert daemon daily recording does not construct `HybridTranscriber` even if stale `.env` contains `HYBRID_TRANSCRIPTION_ENABLED=true`; release docs state WAV capture, FLAC JSON upload, 23 MiB strict guard, 25-minute ceiling, short-WAV fallback, and retained oversize recovery.

- [ ] **Step 2: Confirm RED**

Run: `python -m pytest tests/test_daemon_recovery.py tests/test_release_docs.py tests/test_config.py -q`

Expected: stale hybrid activation and missing documentation failures.

- [ ] **Step 3: Close the obsolete production hybrid switch**

Stop reading `HYBRID_TRANSCRIPTION_ENABLED` and `HYBRID_THRESHOLD_SECONDS` into the daemon production configuration. Keep experimental modules available only to explicit development runners; the normal daemon always calls `process_wav()` once.

- [ ] **Step 4: Update user and release documentation**

Document the exact file lifecycle, JSON request format, safe fallback, preserved-file locations, 25-minute UI/runtime limit, possible post-stop latency, and Windows/macOS real-device release checks. Do not claim those checks have run.

- [ ] **Step 5: Run focused and complete verification**

Run:

```powershell
python -m pytest tests/test_settings.py tests/test_config.py tests/test_settings_dialog.py tests/test_capture_writer.py tests/test_audio_recording.py tests/test_recording_recovery.py tests/test_flac_upload.py tests/test_pipeline_usage.py tests/test_usage_stats.py tests/test_daemon_recovery.py tests/test_parsers.py tests/test_release_docs.py -q
python -m pytest -q -k "not test_paste_text_preserving_clipboard_restores_original_synchronously and not test_paste_text_preserving_clipboard_background_restores_after_delay and not test_empty_masked_key_field_accepts_paste_without_reveal"
python -m pytest tests/test_clipboard.py::test_paste_text_preserving_clipboard_restores_original_synchronously tests/test_clipboard.py::test_paste_text_preserving_clipboard_background_restores_after_delay tests/test_settings_dialog.py::test_empty_masked_key_field_accepts_paste_without_reveal -q
python -m compileall -q speedytype scripts
git diff --check
```

Expected: every command exits 0. Record the real Windows/macOS 24-minute checks as pending release gates.

- [ ] **Step 6: Commit**

```powershell
git add speedytype/config.py speedytype/daemon.py release/README.md MAC_SETUP.md KNOWN_LIMITATIONS.md POC_REPORT.md tests/test_daemon_recovery.py tests/test_release_docs.py tests/test_config.py
git commit -m "docs: prepare full-file FLAC release candidate"
```
