# SpeedyType Active Work

This directory contains approved or in-progress work that has not yet become
current product truth. It is authoritative for implementation scope, but not
for released behavior or user instructions.

## Document Lifecycle

1. Draft and approved designs live in `docs/active/specs/`.
2. Approved implementation plans live in `docs/active/plans/`.
3. After implementation and verification, update the affected sources under
   `docs/current/` so they describe the behavior that actually ships.
4. Move the completed or stopped specification, plan, and dated evidence to
   `docs/archive/`. Archived material is historical and non-authoritative.

A document must not exist in both Active Work and the archive. Work must not
be archived merely because its design was approved; implementation must be
complete or the work must be explicitly stopped first.

## Active Designs and Plans

- [Cross-platform hotkey debounce design](specs/2026-07-18-cross-platform-hotkey-debounce-design.md)
- [Cross-platform hotkey debounce implementation plan](plans/2026-07-18-cross-platform-hotkey-debounce.md)
