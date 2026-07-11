# Known Limitations

This document records limitations that have already been discussed and deliberately deferred, so future work (including future sessions on this project) does not rediscover them as new problems or assume they were simply missed.

Each item lists: current state, known impact, why it was not addressed, and the condition that should trigger re-evaluation.

## 1. Tail latency is ~3.5s, above the original 1.0-1.5s target

- **Current state**: Phase 4 measured real production-path average tail latency at `3.575354s` (min `2.070694s`), with Whisper transcription as the dominant cost (`avg_whisper=2.698143s`). See [PHASE4_REPORT.md](PHASE4_REPORT.md).
- **Known impact**: Every dictation still takes noticeably longer than the original 1.0-1.5s target before pasted text appears.
- **Why not addressed**: Compared against the real-world felt latency of commercial dictation products (e.g. Typeless), this is judged to be in the same rough latency class, not a clear regression. Further optimization was explicitly out of scope for this round.
- **Trigger to re-evaluate**: Real daily usage feels consistently and noticeably slower than alternative tools, or latency worsens further as future phases add features/instrumentation on top of the current pipeline.

## 2. `API` / `BJ 團隊` term-recognition residual error

- **Current state**: Round 2 real-voice validation measured `API` accuracy at `71.4%` and `BJ 團隊` at `83.3%` (all other tracked terms at `100.0%`). See [REAL_VOICE_REPORT_ROUND2.md](REAL_VOICE_REPORT_ROUND2.md). Phase 4 Part B's on/off comparison suggests the LLM polishing stage may sometimes over-correct an already-correct STT output rather than this being purely an STT recognition failure, but that hypothesis has not been root-caused or verified.
- **Known impact**: These two terms have a real, measurable chance of coming out wrong in the final pasted text; user must proofread output when these terms are expected.
- **Why not addressed**: Root-causing whether this is an STT problem, an LLM over-correction problem, or both, was explicitly out of scope for this round; manual correction by the user is the current mitigation.
- **Trigger to re-evaluate**: These two terms cause noticeable real-world friction in daily use, or a future vocabulary expansion requires redesigning the disambiguation approach anyway.

## 3. UAC-elevated window paste behavior is untested

- **Current state**: All four prior phase reports mark elevated/admin windows as `NOT_TESTED` for paste target validation.
- **Known impact**: If the user dictates into an elevated terminal or elevated tool, paste behavior is unverified and may silently fail (elevated windows generally do not accept simulated input from a non-elevated process).
- **Why not addressed**: Automating a UAC prompt interaction safely was judged unsafe/unreliable to script, and out of scope for this round.
- **Trigger to re-evaluate**: The user's daily workflow starts to regularly include elevated windows as a dictation target.

## 4. API keys are stored in plaintext in `.env`

- **Current state**: `OPENAI_API_KEY`, `GEMINI_API_KEY`, and `MINIMAX_API_KEY` are read from a local `.env` file with no OS-level secret protection.
- **Known impact**: Anyone with filesystem read access to this machine/user profile can read the keys directly.
- **Why not addressed**: This is a personal single-user POC; the risk is judged acceptable at this stage, and adding e.g. Windows Credential Manager integration was explicitly out of scope for this round.
- **Trigger to re-evaluate**: The tool moves beyond personal POC use (shared machine, other users, longer-term production use) or the keys' billing scope increases.

## 5. Disambiguation hints show no measurable benefit on the Round 2 dataset

- **Current state**: Phase 4 Part B compared `LLM_DISAMBIGUATION_HINTS=on` vs `off` on the same 16-sample Round 2 set: overall term accuracy was `93.8%` in both cases; `API` accuracy was identical (`71.4%`); `BJ 團隊` was actually better with hints off (`100.0%` vs `83.3%`) in this one run, though the sample is too small to call that a real effect.
- **Known impact**: The prompt hints add complexity and (unverified) marginal token cost without demonstrated accuracy improvement.
- **Why not addressed**: Kept `on` as a conservative default on the reasoning that "probably doesn't hurt" is enough to keep it for now; this round did not attempt further prompt iteration.
- **Trigger to re-evaluate**: A larger real-voice sample shows a consistent, measurable direction (positive or negative), or vocabulary/prompt work is revisited for other reasons.

## 6. Background daemon is a Python process, not a native OS service

- **Current state**: Phase 5 Part B implemented the background daemon (`speedytype/daemon.py`, `python -m speedytype daemon`) as a plain `pythonw.exe` process, controlled via a PID file and `python -m speedytype daemon-stop`, autostarted through a Startup-folder `.bat` script (`speedytype/autostart.py`).
- **Known impact**: Higher memory footprint than a native service; no OS-service semantics (a crashed process does not auto-restart, there is no Windows Service Manager entry, no automatic crash recovery).
- **Why not addressed**: Migrating to a native implementation (e.g. C#/.NET or Rust+Tauri) was explicitly out of scope for this round; for personal daily use, the assumption is that these differences won't be noticeable, and the PID-file/Startup-folder mechanism was simple to implement and easy for the user to understand and disable.
- **Trigger to re-evaluate**: The tool needs to be shared with/handed to other users for longer-term use, or the Python daemon shows real instability in practice (frequent manual restarts needed).

## 7. Windows Task Scheduler autostart was blocked by local policy; Startup-folder script used instead

- **Current state**: The original plan for Part B favored Windows Task Scheduler for autostart. `schtasks /Create` (even for a plain per-user `ONLOGON` trigger, no elevation requested) returned `Access is denied` on this machine, confirmed by running `schtasks` directly outside of any SpeedyType code. The implementation fell back to a `.bat` script in the current user's Startup folder (`%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\SpeedyTypeDaemon.bat`), which requires no elevation and was verified to work.
- **Known impact**: None for the current single-user POC; behavior is equivalent for the "run at logon" use case. It does mean SpeedyType has no Task Scheduler entry, so it won't show up in `taskschd.msc`, only in the Startup folder / `msconfig` startup list.
- **Why not addressed**: This is a working, simpler alternative already recommended as acceptable by the original task brief ("Task Scheduler 或啟動資料夾捷徑皆可"); investigating why this specific machine's local policy blocks `schtasks /Create` was out of scope.
- **Trigger to re-evaluate**: A future environment needs Task Scheduler-specific features (conditional triggers, running while logged off, etc.) that a Startup-folder script cannot provide.

## 8. (Resolved) Combo-hotkey start/end semantics — now confirmed by a live physical key-press test

- **Current state**: The tray-settings round added multi-key hotkey support (`speedytype/daemon.py`, `speedytype/settings_dialog.py`). The design — recording starts when `keyboard.add_hotkey()` reports the full combo pressed, and ends the instant **any one** key of the combo is released — was originally based only on the `keyboard` library's documented behavior (`is_pressed("a+b+c")` true only while all parts are held), with no simulated key events sent (per the user's explicit request, since those affect whatever window has focus system-wide). What *was* verified without OS-level key simulation at the time: countdown-timer/auto-stop logic and Settings-dialog non-blocking behavior (via direct method calls plus in-process monkeypatching of `keyboard.is_pressed`).
- **Update**: The user subsequently ran the live test themselves — captured `ctrl+alt+space` via the Settings dialog, saved, restarted the daemon from the tray, and confirmed holding/releasing the combo starts and stops recording normally. The combo-hotkey design is therefore confirmed working, not just documented-behavior-based.
- **Residual known impact**: None expected for this specific combo. Other never-tried combos (different modifier orderings, Win-key combos, etc.) still rely on the same underlying mechanism and haven't each been individually tested, but the core start/end logic is now verified end-to-end at least once.
- **Trigger to re-evaluate**: If a differently-shaped combo (e.g. three modifiers, or a combo including the Windows key) behaves unexpectedly, revisit this.

## 9. Hotkey conflict detection is a static list, not real-time OS-level detection

- **Current state**: `speedytype/settings_dialog.py`'s `KNOWN_RESERVED_SHORTCUTS` is a small hardcoded set of well-known Windows/app shortcuts (`ctrl+alt+delete`, `ctrl+shift+esc`, `alt+tab`, `win+l`, etc.). The capture widget warns if the newly-captured combo matches this list.
- **Known impact**: A combo that collides with some other running program's own global hotkey, but isn't on this static list, will not be flagged. The `keyboard` library's low-level hook does not raise any registration error for such collisions (both programs simply react to the same keypress), so there is no reliable generic way to detect this without literally triggering the other program's shortcut and observing side effects.
- **Why not addressed**: Real-time conflict probing against arbitrary other software was explicitly out of scope ("不需要解決所有可能衝突，但至少要能偵測並提示使用者"); the static list satisfies the "at least detect the obvious/common cases" bar.
- **Trigger to re-evaluate**: A user reports a hotkey that silently doesn't work or double-triggers another app; add that combo to the static list and/or investigate a more general detection approach.

## 10. Settings-dialog API key editing is a convenience layer only; storage security is unchanged

- **Current state**: This round added masked key fields, a reveal toggle, and a "測試連線" button to the Settings dialog, plus a line-preserving `.env` writer (`speedytype/env_writer.py`) so editing a key no longer requires manually opening `.env` in a text editor.
- **Known impact**: None beyond convenience. The keys are still written to and read from a plaintext `.env` file (see limitation 4); this round did not add any encryption, OS credential-store integration, or access control.
- **Why not addressed**: Out of scope for this round, same reasoning as limitation 4.
- **Trigger to re-evaluate**: Same trigger as limitation 4.

## 11. (Resolved, but note the retroactive impact) Phase 5's Startup-folder autostart likely never actually kept the daemon running

- **Current state**: This is not a live limitation — it is a **fixed** bug, recorded here because it retroactively changes what Phase 5 actually verified. Phase 5's `KNOWN_LIMITATIONS.md` claimed the Startup-folder `.bat` autostart mechanism was verified by manually invoking the script and observing a PID file appear. That check was real, but too short: `pythonw.exe` (used by both the Startup script and, this round, the tray "重新啟動" action) has `sys.stdout = None` with no explicit redirection, and `safe_print()` crashed on its very first call in `run_daemon()`, right after the PID file was written and the tray icon shown. The process died within about a second — long enough to write a PID file, too short to have been caught by that earlier check, which didn't wait or re-check liveness a few seconds later.
- **Known impact (historical)**: Anyone relying on Phase 5's autostart to keep SpeedyType running after logon was very likely getting a daemon that started and then immediately died, silently.
- **Fix applied this round**: `safe_print()` no longer raises when `sys.stdout` is `None` or broken ([speedytype/console.py](speedytype/console.py)); both the Startup `.bat` and the tray restart action now also explicitly redirect stdout/stderr to `speedytype_daemon.log` with UTF-8 encoding forced. Verified with real process checks (`tasklist`, PID file persistence over 9+ seconds, and a correctly-encoded log file after a real `.bat` invocation) — see the "Bug found and fixed" note in `POC_REPORT.md`'s Phase 6 section.
- **Trigger to re-evaluate**: None expected — this is closed. Listed here so nobody re-reads Phase 5's original autostart claim at face value without seeing this correction.

## 12. Recording device is matched by exact name; duplicate names across host APIs resolve to the first enumeration match

- **Current state**: `speedytype/config.py`'s `resolve_mic_device_setting()` and `speedytype/audio.py`'s `find_input_device_index_by_name()` match a saved device name against `sounddevice.query_devices()` by exact string equality. On this test machine, the same physical microphone appears multiple times under different host APIs (e.g. `Microphone (AT-CSP1)` appears at 4 different indices — MME, WDM-KS, etc.). When the user selects that name in the Settings dialog, resolution always picks the **first** matching index in enumeration order, not necessarily the specific host-API variant the user might have had in mind.
- **Known impact**: For most users this is invisible (the different host-API variants of the same physical device behave equivalently for basic recording), and on this test machine the first match happened to already be the system default. It could matter if a specific host API variant behaves differently (e.g. different exclusive-mode behavior, different default sample rate) and the user needed that specific one rather than "whichever one enumerates first with this name."
- **Why not addressed**: Disambiguating identically-named devices (e.g. by showing host API alongside the name) was not part of this round's scope, which explicitly asked to keep the device name (not index) as the stored identifier for stability across reboots/replugs.
- **Trigger to re-evaluate**: A user reports that device selection picks "the wrong" instance of a device that appears multiple times, or a future need arises to distinguish host-API variants in the picker UI.

## 13. (Resolved) Phase 5's AEC-blocked volume-bar verification gap

- **Current state**: Phase 5 could not confirm the volume-reactive bars respond to real loudness contrast, because the only microphone available for automated testing is part of an "AT-CSP1" conferencing speakerphone with acoustic echo cancellation, which suppressed its own played-back test audio from reaching its own mic feed. Phase 8 closed this gap: the user held the hotkey and spoke live, first at normal volume then noticeably louder, and confirmed the pill's bars visibly rose higher during the louder pass. This is a genuine real-voice, real-hardware confirmation, not a workaround.
- **Trigger to re-evaluate**: None expected — closed. Listed here so the Phase 5 gap isn't mistaken for still-open.

## 14. (Resolved) No single-instance guard allowed two daemons to briefly hold the same global hotkey

- **Current state**: Before Phase 8, `run_daemon()` wrote its PID file unconditionally with no check for an existing live daemon, so nothing prevented starting a second instance (e.g. via the tray "重新啟動" action, which spawns a new process before the old one fully quits) — both processes could briefly hold `keyboard.add_hotkey()` for the same combo. Phase 8 added `check_existing_daemon()`: a stale PID file (process no longer running, e.g. after a crash) is now detected and cleaned up automatically before starting; a genuinely live PID causes the new attempt to refuse to start with a clear message instead. `restart_daemon()` was also fixed to remove its own PID file before spawning the replacement, so the new process's startup check doesn't mistake the still-quitting old process for a conflict.
- **Trigger to re-evaluate**: None expected — closed, verified with real process checks (stale PID auto-cleaned and started; genuinely running PID correctly refused a second instance; full restart cycle completes with exactly one live process throughout).

## 15. Whisper collapses an exact short phrase repeated back-to-back within one continuous recording

- **Current state**: During Phase 8 live testing, the user held the hotkey once and said "測試1、2、3、4" three times in a row within a single ~8.58s recording. The raw Whisper transcript contained only **one** instance of the phrase, not three — confirmed from the daemon's own log (`Whisper raw transcript: 測試 1、2、3、4`), so the loss happens at the Whisper API stage itself, before Gemini polishing ever sees the text (Gemini's output was identical to the raw transcript — it passed through what it received unchanged). This is distinct from and does not contradict Phase 8's Test 2 result, where three *different* short sentences spoken in three *separate* recordings all transcribed correctly with no loss.
- **Known impact**: Narrow — only affects the specific pattern of repeating the exact same short phrase multiple times with no other content in between, inside one continuous recording. Ordinary dictation (varied sentences, or the same content spoken once per recording) is unaffected, as demonstrated by every other real-voice test across Phases 5-8.
- **Why not addressed**: This looks like a known Whisper API behavior (suppressing/collapsing near-identical repeated short segments, a documented quirk of its decoding), not a bug in this project's code — nothing in the prompt, vocab bias, or LLM polishing stage is involved, since the raw transcript was already short one repetition. Root-causing or working around a third-party model's decoding behavior is out of scope for this round.
- **Trigger to re-evaluate**: A real dictation use case (not just a deliberate test) involves saying the same short phrase multiple times in one breath/recording and losing content matters in practice.

## 16. Gemini polishing occasionally drops numbers/repeated content from garbled input — investigated, found to be non-deterministic, no fix applied yet

- **Current state**: A follow-up to item 15. The user repeated a numbers-first phrase ("123 test") three times within one continuous recording, in English this time. Unlike item 15, Whisper's raw transcript this time *did* preserve fragments of all three repetitions, including the numbers (`123測試測試 123測試測試 123 test 123 test`) — but Gemini's polishing stage collapsed all of that down to just `測試。`, discarding every number and the repetition, even though the raw material was there to work with. This pointed at the LLM prompt (not Whisper) as the loss point for this specific case.
  - To investigate a fix, a candidate prompt rule was drafted (an explicit instruction to preserve numbers/distinct content when consolidating repeated or garbled STT output) and A/B tested against the exact same captured raw transcript, calling the Gemini API directly (bypassing the need for more live speech).
  - First single-sample comparison: current prompt → `測試。` (numbers lost, matching the live failure); candidate prompt → `123測試，123 test。` (numbers preserved) — looked like a real fix.
  - A repeated-trials follow-up (8x each prompt on the identical input) contradicted this: the **unmodified current prompt** preserved the numbers in 6/6 valid completions. The remaining 2/8 current-prompt attempts and 7/8 candidate-prompt attempts failed with `429 quota exceeded` (Gemini API quota exhaustion from the volume of test calls in this investigation), not content failures — so the candidate prompt has only 1 valid sample, not enough to compare against.
- **Known impact**: The one live failure (`測試。`) appears to have been rare sampling variance in Gemini's output for genuinely garbled/repeated input, rather than a reliably reproducible bug in the current prompt — the same prompt preserved numbers correctly 6/6 times when retested. No regression was found in the candidate prompt either (self-correction, filler removal, list formatting, and a natural stutter-repeat case all produced identical output to the current prompt), but there isn't enough evidence to say it measurably *improves* the failure rate versus just being additional prompt complexity with an unproven benefit.
- **Why not addressed**: The investigation was cut short by hitting the Gemini API's request quota before a fair, adequately-sampled comparison could be completed. Applying a prompt change on the strength of a single favorable sample (which is exactly what looked like a fix at first) would not meet this project's own evidence bar. Left as an open decision for the user rather than guessed at.
- **Trigger to re-evaluate**: Once API quota resets, re-run the repeated-trials comparison (`scripts/test_prompt_variants_repeated.py`, `scripts/test_prompt_variants.py` — both already written) with a larger sample size for the candidate prompt specifically, to get a real failure-rate comparison. Alternatively, if this pattern (repeated numeric/garbled content within one recording) recurs often enough in real usage to matter, that alone is enough reason to apply the candidate prompt as low-cost insurance even without statistically strong proof it helps.

### 2026-07-11 follow-up

- A new repeated run produced 4/4 valid current-prompt samples preserving numbers. The other 4 current attempts and all 8 candidate attempts returned HTTP 429 quota errors. The candidate therefore still has no new valid evidence and cannot be compared fairly.
- The script now excludes API errors from semantic success rates. The candidate prompt remains unapplied until at least 5-6 valid candidate samples are available.

## 17. macOS clipboard restoration is text-only

- **Current state**: The macOS backend snapshots and restores only text through `pyperclip`; Windows continues to preserve all writable clipboard formats.
- **Known impact**: If the macOS clipboard initially contains an image, file list, rich text, or application-specific format, a SpeedyType paste cannot restore those non-text formats.
- **Why not addressed**: Full `NSPasteboard` multi-format migration would require substantially more AppKit-specific code and is unnecessary for the personal text-dictation goal.
- **Trigger to re-evaluate**: Daily use regularly overwrites non-text clipboard content that must be preserved.

## 18. macOS backends are implemented but require real-Mac verification

- **Windows-verified**: platform dispatch, canonical hotkey migration, Windows hold/release behavior, clipboard preservation, psutil process handling, Startup install/query/uninstall, Settings checkbox, daemon smoke, and latency regression.
- **Unit-tested only**: macOS text clipboard contract, chord state semantics, LaunchAgent plist and launchctl arguments, and permission-error guidance.
- **Must be tested on the Mac**: deny then grant Accessibility/Input Monitoring; hold the configured chord to start and release any key to stop; timeout stop; Cmd+V into at least two applications; text clipboard restoration; Settings shortcut capture and reserved warnings; LaunchAgent install/query/remove and logout/login persistence; tray/settings behavior; overlay click-through/topmost behavior on normal desktops, Spaces, and Mission Control.
- **Trigger to re-evaluate**: Complete this checklist on the target Mac and record actual results before describing macOS support as verified.

## 19. Long-recording quasi-streaming is promising but not enabled in production

- **Original concern**: The first 262.208s case concatenated the two shorter recordings, whose meeting topics and technical terms overlap. It was therefore vulnerable to both content similarity and splice artifacts and is not used as the decisive length result.
- **Replacement evidence**: A 294.792s continuous TTS recording reads one complete, non-repeating travel narrative. In the same three-case rerun, batch/quasi tails were 7.785/2.127s (126s), 7.329/3.444s (134s), and 18.098/1.874s (295s), improvements of 72.7%, 53.0%, and 89.6%. The long-case improvement remains and grows after removing the splice confounder.
- **Trade-off**: The 295s quasi path used 12 requests totaling 34.742s versus one 18.098s batch request, about 1.92x request work. Spot inspection also found omissions and boundary merge errors in the quasi transcript, so lower tail does not yet imply acceptable output quality.
- **Decision**: A hybrid path above roughly 60-90 seconds is worth developing, and the observed latency trend is not an artifact of the composite file. Production remains batch-only until chunk merge quality and the final Gemini/paste output pass a dedicated comparison.
- **Evidence**: `long_recording_results_continuous.jsonl`, `test_audio_long/continuous_tts_script.txt`, and `test_audio_long/manifest.json`. The earlier `long_recording_results.jsonl` is retained as superseded evidence.
