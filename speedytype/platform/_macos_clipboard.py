from __future__ import annotations

from dataclasses import dataclass
import time

import pyperclip

from ._macos_event_tap import SPEEDYTYPE_EVENT_MARKER


@dataclass(frozen=True)
class ClipboardSnapshot:
    ok: bool
    text: str = ""
    error: str = ""


@dataclass(frozen=True)
class PasteTarget:
    bundle_identifier: str = ""
    process_identifier: int = 0


def snapshot_clipboard() -> ClipboardSnapshot:
    try:
        return ClipboardSnapshot(ok=True, text=pyperclip.paste())
    except Exception as exc:
        return ClipboardSnapshot(ok=False, error=str(exc))


def restore_clipboard(snapshot: ClipboardSnapshot) -> tuple[bool, str]:
    if not snapshot.ok:
        return False, f"Skipped restore: snapshot was not captured ({snapshot.error})."
    try:
        pyperclip.copy(snapshot.text)
    except Exception as exc:
        return False, f"Could not restore clipboard text: {exc}"
    return True, "Clipboard text restored."


def send_paste_shortcut(*, quartz=None) -> None:
    if quartz is None:
        import Quartz as quartz

    for keycode, is_down in ((55, True), (9, True), (9, False), (55, False)):
        event = quartz.CGEventCreateKeyboardEvent(None, keycode, is_down)
        quartz.CGEventSetIntegerValueField(
            event,
            quartz.kCGEventSourceUserData,
            SPEEDYTYPE_EVENT_MARKER,
        )
        quartz.CGEventSetFlags(event, quartz.kCGEventFlagMaskCommand)
        quartz.CGEventPost(quartz.kCGHIDEventTap, event)


def _appkit(value=None):
    if value is not None:
        return value
    import AppKit

    return AppKit


def capture_paste_target(*, appkit=None) -> PasteTarget | None:
    try:
        application = _appkit(appkit).NSWorkspace.sharedWorkspace().frontmostApplication()
        if application is None:
            return None
        bundle_identifier = str(application.bundleIdentifier() or "")
        process_identifier = int(application.processIdentifier() or 0)
    except Exception:
        return None
    if process_identifier <= 0 and not bundle_identifier:
        return None
    return PasteTarget(
        bundle_identifier=bundle_identifier,
        process_identifier=process_identifier,
    )


def focus_paste_target(target: PasteTarget | None, *, appkit=None) -> tuple[bool, str, float]:
    if target is None:
        return True, "No paste target captured.", 0.0

    started = time.perf_counter()
    try:
        kit = _appkit(appkit)
        running_application = None
        if target.process_identifier > 0:
            running_application = (
                kit.NSRunningApplication.runningApplicationWithProcessIdentifier_(
                    target.process_identifier
                )
            )
        if running_application is None:
            return (
                False,
                "Captured paste target application is no longer running.",
                time.perf_counter() - started,
            )
        options = getattr(kit, "NSApplicationActivateIgnoringOtherApps", 1)
        activated = bool(running_application.activateWithOptions_(options))
        elapsed = time.perf_counter() - started
        if not activated:
            return False, "Could not restore captured paste target application.", elapsed
        return True, "Restored captured paste target application.", elapsed
    except Exception as exc:
        return False, f"Could not restore paste target: {type(exc).__name__}.", time.perf_counter() - started
