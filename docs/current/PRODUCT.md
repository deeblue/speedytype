# SpeedyType Product

## Purpose

SpeedyType turns a configurable keyboard action into polished text in the
application the user is already working in. It is designed for occasional
short dictation and longer thought capture without requiring a browser-based
recording workflow.

## User Problem

Desktop users often need to capture speech without breaking focus, repeatedly
copying text between applications, or exposing credentials in command lines and
configuration files. Long recordings add two further risks: an unclear
recording state and loss of the original audio when downstream processing
fails.

## Primary Workflow

1. Configure credentials, microphone, hotkey, Hold/Toggle mode, and optional
   LLM polishing in Settings.
2. Start the background daemon.
3. Hold the recording key, or press it once in Toggle mode, while the recording
   pill shows elapsed time.
4. Stop manually or at the configured ceiling.
5. SpeedyType preserves the WAV, validates a lossless upload, transcribes and
   optionally polishes the text, pastes it, and restores the clipboard.

## Product Principles

- Preserve recoverable user audio before optimizing latency.
- Fail closed at upload and processing boundaries; never silently discard a
  recoverable recording.
- Keep secrets in the operating-system credential store and keep pasteable key
  fields masked by default.
- Make recording state, time limit, estimated usage, budget, and remaining
  capacity visible.
- Use the same core behavior on Windows and macOS while respecting each
  platform's native hotkey, tray/menu, permission, and clipboard boundaries.

## Supported Platforms

SpeedyType supports Windows 10/11 and macOS with Python 3.13 or newer. Windows
uses a system-tray integration and Windows-specific hotkey/paste mechanisms;
macOS uses a menu-bar accessory application, native Quartz event tap, and
macOS privacy permissions.

## Differentiation

The project combines desktop hotkey capture, explicit Hold/Toggle controls,
durable local recording, complete-file transcription, optional LLM polishing,
clipboard preservation, system-keyring credentials, and local cost/capacity
feedback in one small source-deployable application.

## Success Criteria

- The intended hotkey starts and stops exactly one recording.
- The user can always see when daemon recording is active and when it will stop.
- Empty input and downstream failures do not crash the daemon or silently lose
  recoverable audio.
- Accepted uploads preserve the captured PCM exactly through lossless encoding.
- Text reaches the active application while prior clipboard text is restored.
- Setup, update, command discovery, credential storage, and diagnostics remain
  reproducible on both supported platforms.
