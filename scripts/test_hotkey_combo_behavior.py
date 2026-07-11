from __future__ import annotations

import time

import keyboard


def check_add_hotkey_fires(combo: str) -> None:
    fired = {"count": 0}

    def callback():
        fired["count"] += 1

    handle = keyboard.add_hotkey(combo, callback, suppress=False)
    try:
        parts = combo.split("+")
        for key in parts:
            keyboard.press(key)
            time.sleep(0.05)
        time.sleep(0.2)
        print(f"ADD_HOTKEY combo={combo!r} fired_count_after_press={fired['count']}")

        # Hold for a bit to see if auto-repeat causes it to fire again.
        time.sleep(0.5)
        print(f"ADD_HOTKEY combo={combo!r} fired_count_after_hold={fired['count']}")

        for key in reversed(parts):
            keyboard.release(key)
            time.sleep(0.05)
        time.sleep(0.2)
        print(f"ADD_HOTKEY combo={combo!r} fired_count_after_release={fired['count']}")
    finally:
        keyboard.remove_hotkey(handle)
        for key in combo.split("+"):
            try:
                keyboard.release(key)
            except Exception:
                pass


def check_is_pressed_release_semantics(combo: str) -> None:
    parts = combo.split("+")
    for key in parts:
        keyboard.press(key)
        time.sleep(0.05)
    time.sleep(0.1)
    print(f"IS_PRESSED combo={combo!r} all_down={keyboard.is_pressed(combo)}")

    # Release only the FIRST key in the combo (not all), keep the rest held.
    first_key = parts[0]
    keyboard.release(first_key)
    time.sleep(0.1)
    print(f"IS_PRESSED combo={combo!r} after_releasing_first_key({first_key!r})={keyboard.is_pressed(combo)}")

    # Clean up: release everything else.
    for key in parts[1:]:
        try:
            keyboard.release(key)
        except Exception:
            pass
    time.sleep(0.1)
    print(f"IS_PRESSED combo={combo!r} after_releasing_all={keyboard.is_pressed(combo)}")


def main() -> int:
    for combo in ["ctrl+alt+space", "ctrl+shift+f9"]:
        print(f"--- {combo} ---")
        check_add_hotkey_fires(combo)
        time.sleep(0.3)
        check_is_pressed_release_semantics(combo)
        time.sleep(0.3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
