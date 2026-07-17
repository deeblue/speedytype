from __future__ import annotations


def _appkit(value=None):
    if value is not None:
        return value
    import AppKit

    return AppKit


def configure_daemon_application(*, appkit=None) -> None:
    kit = _appkit(appkit)
    kit.NSApplication.sharedApplication().setActivationPolicy_(
        kit.NSApplicationActivationPolicyAccessory
    )


def activate_window(window, *, appkit=None) -> None:
    window.show()
    window.raise_()
    window.activateWindow()
    _appkit(appkit).NSApplication.sharedApplication().activateIgnoringOtherApps_(True)
