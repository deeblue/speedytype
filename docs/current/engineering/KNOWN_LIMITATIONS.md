# Known Limitations

Only limitations that remain true are listed here. Dated and resolved items are
preserved in the [2026-07-18 snapshot](../../archive/reports/KNOWN_LIMITATIONS-2026-07-18.md).

## macOS native integration still requires real-device acceptance

- **Impact:** The Quartz event tap, AppKit menu-bar/accessory behavior, privacy
  prompts, settings hotkey capture, paste, restart, and bounded automatic stop
  are implemented and automated where possible, but final v0.5.7 acceptance
  remains pending on a real Mac.
- **Workaround:** Follow the real-Mac checklist in
  [MAC_SETUP.md](../user/MAC_SETUP.md) before publishing the release tag.
- **Removal condition:** The complete checklist passes on the target Mac without
  a new Python `.ips` crash report.

## macOS permissions can be tied to a Python executable path

- **Impact:** A newly extracted release or recreated venv can cause macOS to ask
  again for Input Monitoring, Accessibility, or Microphone access.
- **Workaround:** Reauthorize the current `.venv/bin/python` or terminal under
  System Settings > Privacy & Security, then fully restart the daemon.
- **Removal condition:** A signed native distribution provides a stable identity
  across upgrades and passes the same hotkey/paste acceptance flow.

## Post-stop complete-file processing has visible latency

- **Impact:** Lossless encoding and the authoritative complete-file
  transcription occur after stop, so output is not immediate, especially for a
  long recording.
- **Workaround:** Keep the processing warning visible and wait for the normal
  paste or retained-failure notification; do not restart the daemon while it is
  processing.
- **Removal condition:** A quality-equivalent progressive path meets the
  complete-file transcript floor without introducing segmentation loss.

## Recording durability does not claim sudden-power-loss survival

- **Impact:** Durable WAV/sidecar handling protects recoverable data across
  processing failures and process/OS crashes, but data still buffered by the OS
  or storage device may be lost during abrupt power removal.
- **Workaround:** Use reliable local storage and power protection for critical
  recordings; review `failed-retained` artifacts after abnormal termination.
- **Removal condition:** A tested sync/journaling design demonstrates the stated
  power-loss durability guarantee on supported filesystems.

## Clipboard preservation is text-only on macOS

- **Impact:** The macOS restore path preserves text clipboard content but does
  not reconstruct arbitrary rich or application-specific pasteboard formats.
- **Workaround:** Avoid running a paste operation while non-text clipboard data
  must be preserved exactly.
- **Removal condition:** The macOS backend snapshots and restores required
  pasteboard types with real-device regression coverage.

## Paste into elevated Windows applications is not verified

- **Impact:** A non-elevated daemon may be unable to inject input into a
  UAC-elevated target window.
- **Workaround:** Paste into a non-elevated application or manually paste the
  produced clipboard text.
- **Removal condition:** An approved privilege-boundary design and automated
  acceptance test cover elevated targets safely.

## Hotkey conflict detection is advisory

- **Impact:** Settings checks a static list and cannot prove that another
  application has registered the same shortcut at runtime.
- **Workaround:** Choose a different shortcut if activation is unreliable and
  restart the daemon after saving it.
- **Removal condition:** Each platform provides a safe real-time registration or
  conflict probe integrated with Settings.

## Duplicate recording-device names select the first match

- **Impact:** Settings hides duplicate display names after the first selectable
  mono 16 kHz input device. If multiple host APIs expose the same microphone
  name, exact-name configuration can still resolve to the first enumerated
  matching device rather than the intended instance.
- **Workaround:** Choose a uniquely named device where possible and verify it in
  Settings before a long recording. Use `speedytype list-audio-devices` when raw
  PortAudio evidence is needed.
- **Removal condition:** Device configuration persists a stable backend/device
  identifier in addition to the display name.
