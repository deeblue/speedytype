# SpeedyType Decision Register

This register summarizes accepted production decisions. Linked archive files
retain the dated reasoning and measurements.

## 2026-07-14 — Store secrets in the system keyring

- **Status:** Accepted
- **Decision:** Store API keys in Windows Credential Manager or macOS Keychain,
  while supporting controlled migration from legacy `.env` values.
- **Rationale:** OS credential stores reduce plaintext-secret exposure without
  breaking existing installs.
- **Rejected alternatives:** Continuing to use `.env` as the primary store and
  requiring users to re-enter keys on every start.
- **Evidence:** [Keyring and usage design](../../archive/specs/2026-07-14-keyring-usage-cost-design.md)

## 2026-07-15 — Build an allowlisted source release and short command wrapper

- **Status:** Accepted
- **Decision:** Generate a deterministic, minimal source release and install a
  `speedytype` wrapper that injects the correct Python and default config paths
  while forwarding all user arguments.
- **Rationale:** Users need a clean distributable and a practical manual command
  without exposing secrets or internal test artifacts.
- **Rejected alternatives:** Shipping the development tree and requiring the
  full `python -m speedytype --env ...` command.
- **Evidence:** [Source release design](../../archive/specs/2026-07-15-source-release-design.md) and [command alias design](../../archive/specs/2026-07-15-command-alias-design.md)

## 2026-07-16 — Use native macOS hotkey and accessory application boundaries

- **Status:** Accepted
- **Decision:** Use a Quartz event tap for the daemon hotkey and AppKit accessory
  policy for menu-bar operation without a Python Dock icon.
- **Rationale:** Native event and application-lifecycle behavior matches macOS
  permissions and avoids the instability observed with the earlier path.
- **Rejected alternatives:** Cross-platform keyboard hooks as the primary macOS
  listener and a normal foreground Python application for the daemon.
- **Evidence:** [macOS native stability design](../../archive/specs/2026-07-16-macos-native-hotkey-stability-design.md)

## 2026-07-17 — Use complete-file `whisper-1` JSON transcription

- **Status:** Accepted
- **Decision:** Send one admitted complete lossless file to `whisper-1` using
  JSON without timestamp output.
- **Rationale:** Complete-file lossless transcription was the only evaluated
  path that consistently preserved the established transcript-quality floor;
  fine-grained segmentation added quality and merge risk without material tail
  benefit at the tested duration.
- **Rejected alternatives:** Lossy upload, promptless or prompt-chained
  fine-grained chunks, hybrid merging, alternate hosted models, and local CPU
  transcription for the production latency path.
- **Evidence:** [Long-recording investigation](../../archive/experiments/long-recording/2026-07-16_long-recording-hybrid-transcription-investigation.md)

## 2026-07-18 — Use durable WAV and validated lossless FLAC

- **Status:** Accepted
- **Decision:** Capture WAV first, validate a lossless FLAC against exact samples
  and decoded PCM, require actual size `<23 MiB`, and retain the WAV on failure.
- **Rationale:** This separates durable user evidence from upload efficiency and
  enforces fail-closed admission below the provider boundary.
- **Rejected alternatives:** Recording directly to a compressed container,
  lossy upload, optimistic size estimation, or discarding the WAV after an
  unsuccessful processing stage.
- **Evidence:** [Full-file FLAC design](../../archive/specs/2026-07-17-full-file-flac-long-recording-design.md)

## 2026-07-18 — Offer Hold and Toggle with a 25-minute ceiling

- **Status:** Accepted
- **Decision:** Keep Hold as the default, offer Toggle with release-to-rearm,
  display recording time/countdown, and use one guarded automatic-stop path at
  25 minutes.
- **Rationale:** Toggle makes long capture practical, while visible state and a
  hard ceiling prevent forgotten recordings and oversize uploads.
- **Rejected alternatives:** Requiring continuous press for every recording,
  allowing unbounded Toggle recording, or stopping without a local warning.
- **Evidence:** [Toggle recording design](../../archive/specs/2026-07-18-toggle-recording-overlay-design.md)

## 2026-07-18 — Treat Windows automation as evidence and macOS as the hardware gate

- **Status:** Accepted
- **Decision:** Use Windows simulation/automation as completion evidence and
  retain one bounded-duration real-macOS integration gate with no minimum live
  recording duration.
- **Rationale:** Windows capture and state invariants are automatable in the
  development environment; macOS permissions, event tap, menu-bar/Dock, paste,
  and lifecycle behavior require real hardware.
- **Rejected alternatives:** Keeping a duplicate Windows hardware gate or
  requiring a 24/25-minute live recording when bounded automatic stop can prove
  the integration behavior.
- **Evidence:** [macOS-only release-gate plan](../../archive/plans/2026-07-18-macos-only-release-gate.md)
