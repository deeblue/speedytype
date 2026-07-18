# SpeedyType Current Status

**As of:** 2026-07-18  
**Current code version:** 0.5.3  
**Build date:** 2026-07-16  
**Target release candidate:** 0.5.4

## Implemented

- System keyring storage with legacy `.env` migration and pasteable masked key
  input.
- Windows and macOS short command wrapper and platform-specific daemon
  integration.
- Hold and Toggle recording modes, elapsed recording overlay, final 60-second
  countdown, 25-minute automatic stop, and pill-local stop warning.
- Settings-window SpeedyType application identity, filtered recording-device
  picker, and wheel-safe recording mode/device selectors.
- Cross-platform 80 ms hotkey qualification with immediate provisional capture,
  delayed recording UI, safe rejected-artifact cleanup, and persistent
  privacy-safe rejection diagnostics.
- Durable PCM16 WAV capture/recovery, validated lossless FLAC conversion,
  strict `<23 MiB` admission, complete-file `whisper-1` JSON transcription,
  and retained failure artifacts.
- LLM polishing, clipboard preservation, automatic paste, usage/cost history,
  monthly budget controls, and capacity visualization.

## Verification State

- Windows simulation and automation are completion evidence; Windows is not a
  hardware release gate.
- macOS is the only hardware release gate.
- No 24- or 25-minute real recording is required; the macOS gate exercises
  bounded-duration automatic stop and the documented interaction/permission
  flow.
- Automated Qt coverage includes recording pill state/render smoke tests.
  Real macOS verification still checks Dock/menu-bar identity, device picker
  behavior, selector scrolling, and pill visuals with native fonts/scaling.

## Next Actions

1. Run the documented macOS real-device acceptance procedure.
2. Update `speedytype/version.py` only when cutting the accepted 0.5.4 release.
