# Settings Device and Overlay Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the settings-window application identity, reduce and harden the recording-device selector, prevent accidental combo-box changes while scrolling, and verify the long-recording pill UI across Windows and macOS scope.

**Architecture:** Keep the recording pipeline unchanged. Add small UI/platform helpers around the existing Qt application setup, add a selectable-device listing API beside the raw diagnostic listing API, use a focused no-wheel combo-box subclass in the settings dialog, and strengthen automated overlay checks while leaving macOS real-device visual acceptance as an explicit gate.

**Tech Stack:** Python 3.13, PyQt6, sounddevice/PortAudio, pytest, existing SpeedyType settings and daemon UI modules.

## Global Constraints

- Do not change capture, transcription, FLAC/WAV, hotkey debounce, keyring, usage-cost, or daemon state-machine behavior.
- Windows and macOS behavior must be considered for every user-facing UI change.
- Keep `list-audio-devices` useful for diagnostics; do not hide raw device evidence from the CLI unless a separate flag is added.
- The settings UI should prefer system default plus devices that SpeedyType can open with its production input format: `samplerate=16000`, `channels=1`.
- Device selection must remain stored by device name, not index, until the separate stable device identity limitation is addressed.
- The recording pill must stay click-through, bottom-center, and always-on-top.
- macOS real-device checks remain manual acceptance gates when they require a real Dock/menu-bar/window-manager environment.

---

## File Structure

- Modify `speedytype/platform/app.py`: expose app identity setup used by standalone settings and daemon UI paths.
- Modify `speedytype/platform/_windows_app.py`: set a stable Windows AppUserModelID before creating or showing windows.
- Modify `speedytype/platform/_macos_app.py`: keep daemon accessory behavior and add standalone GUI identity support without forcing daemon windows into the Dock.
- Modify `speedytype/settings_launcher.py`: apply app identity and application icon before opening standalone settings.
- Modify `speedytype/daemon.py`: verify daemon-created settings/about windows still share the SpeedyType icon path.
- Modify `speedytype/audio.py`: add selectable-device filtering while keeping raw diagnostic enumeration.
- Modify `speedytype/settings_dialog.py`: use selectable devices and no-wheel combo boxes.
- Modify `speedytype/overlay.py`: add testable text bounding helpers only if current paint logic cannot be verified without them.
- Modify `docs/current/user/README.md`, `docs/current/user/MAC_SETUP.md`, and `docs/current/engineering/KNOWN_LIMITATIONS.md`: document changed device picker behavior and macOS visual acceptance.
- Test files: `tests/test_platform_app.py`, `tests/test_settings_launcher.py`, `tests/test_audio_devices.py` or existing `tests/test_audio_recording.py`, `tests/test_settings_dialog.py`, `tests/test_overlay.py`, `tests/test_release_docs.py`.

## Task 1: Standalone Settings App Identity

**Files:**
- Modify: `speedytype/platform/app.py`
- Modify: `speedytype/platform/_windows_app.py`
- Modify: `speedytype/platform/_macos_app.py`
- Modify: `speedytype/settings_launcher.py`
- Test: `tests/test_platform_app.py`
- Test: `tests/test_settings_launcher.py`

**Interfaces:**
- Produces: `configure_standalone_application_identity() -> None`
- Consumes: existing `build_app_icon() -> QIcon`

- [ ] **Step 1: Write failing platform identity tests**

Add tests proving Windows receives an AppUserModelID call and macOS standalone setup does not use daemon accessory policy:

```python
def test_windows_standalone_identity_sets_app_user_model_id(monkeypatch):
    calls = []

    class FakeShell32:
        def SetCurrentProcessExplicitAppUserModelID(self, value):
            calls.append(value)
            return 0

    class FakeWindll:
        shell32 = FakeShell32()

    monkeypatch.setattr(_windows_app.ctypes, "windll", FakeWindll())

    _windows_app.configure_standalone_application_identity()

    assert calls == ["SpeedyType.SpeedyType"]


def test_macos_standalone_identity_does_not_force_accessory_policy():
    appkit = FakeAppKit()

    _macos_app.configure_standalone_application_identity(appkit=appkit)

    assert appkit.app.calls == []
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```powershell
python -m pytest -q tests/test_platform_app.py::test_windows_standalone_identity_sets_app_user_model_id tests/test_platform_app.py::test_macos_standalone_identity_does_not_force_accessory_policy
```

Expected: FAIL because `configure_standalone_application_identity` does not exist.

- [ ] **Step 3: Implement platform identity helpers**

Add to `speedytype/platform/app.py`:

```python
def configure_standalone_application_identity() -> None:
    if sys.platform == "darwin":
        from ._macos_app import configure_standalone_application_identity as implementation
    elif sys.platform == "win32":
        from ._windows_app import configure_standalone_application_identity as implementation
    else:
        return None
    return implementation()
```

Add to `speedytype/platform/_windows_app.py`:

```python
import ctypes


APP_USER_MODEL_ID = "SpeedyType.SpeedyType"


def configure_standalone_application_identity() -> None:
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        return None
```

Add to `speedytype/platform/_macos_app.py`:

```python
def configure_standalone_application_identity(*, appkit=None) -> None:
    return None
```

- [ ] **Step 4: Wire standalone settings launcher**

Update `speedytype/settings_launcher.py` so identity is configured before `QApplication` is constructed and the app icon is set on the application object:

```python
from speedytype.icon import build_app_icon
from speedytype.platform.app import configure_standalone_application_identity


def show_settings_dialog(env_path: str | Path | None = None) -> int:
    config = load_config(env_path, require_api_keys=False)
    configure_standalone_application_identity()
    application = QApplication.instance()
    if application is None:
        application = QApplication(sys.argv)
    application.setApplicationName("SpeedyType")
    application.setWindowIcon(build_app_icon())
    dialog = SettingsDialog(config, env_path, None)
    dialog.exec()
    return 0
```

- [ ] **Step 5: Update launcher tests**

Extend the fake application in `tests/test_settings_launcher.py`:

```python
class FakeApplication:
    icon_calls = []
    name_calls = []

    @staticmethod
    def instance():
        return object()

    def setWindowIcon(self, icon):
        self.icon_calls.append(icon)

    def setApplicationName(self, name):
        self.name_calls.append(name)
```

Patch `configure_standalone_application_identity` and `build_app_icon` so the test asserts call order without needing real Qt.

- [ ] **Step 6: Verify**

Run:

```powershell
python -m pytest -q tests/test_platform_app.py tests/test_settings_launcher.py
```

Expected: PASS.

## Task 2: Selectable Recording Device Filtering

**Files:**
- Modify: `speedytype/audio.py`
- Modify: `speedytype/settings_dialog.py`
- Test: `tests/test_audio_devices.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Produces: `list_selectable_input_devices() -> list[dict[str, object]]`
- Produces: `_is_selectable_input_device(index: int, device: dict[str, object]) -> bool`
- Consumes: existing `list_input_devices()` for raw CLI diagnostics.

- [ ] **Step 1: Write failing audio filtering tests**

Create `tests/test_audio_devices.py`:

```python
from speedytype import audio


def test_selectable_devices_excludes_unopenable_and_generic_aliases(monkeypatch):
    devices = [
        {"name": "Microsoft Sound Mapper - Input", "max_input_channels": 2, "hostapi": 0, "default_samplerate": 44100.0},
        {"name": "Primary Sound Capture Driver", "max_input_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
        {"name": "Microphone Array", "max_input_channels": 2, "hostapi": 1, "default_samplerate": 44100.0},
        {"name": "Stereo Mix", "max_input_channels": 2, "hostapi": 2, "default_samplerate": 48000.0},
        {"name": "Speakers", "max_input_channels": 0, "hostapi": 2, "default_samplerate": 48000.0},
    ]

    monkeypatch.setattr(audio.sd, "query_devices", lambda: devices)

    def fake_check_input_settings(*, device, samplerate, channels):
        assert samplerate == audio.SAMPLE_RATE
        assert channels == audio.CHANNELS
        if device == 3:
            raise audio.sd.PortAudioError("Invalid sample rate")

    monkeypatch.setattr(audio.sd, "check_input_settings", fake_check_input_settings)

    assert [item["name"] for item in audio.list_selectable_input_devices()] == ["Microphone Array"]
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_audio_devices.py
```

Expected: FAIL because `list_selectable_input_devices` does not exist.

- [ ] **Step 3: Implement selectable filtering**

Add to `speedytype/audio.py`:

```python
GENERIC_INPUT_DEVICE_NAMES = {
    "microsoft sound mapper - input",
    "primary sound capture driver",
}


def _is_generic_input_alias(name: str) -> bool:
    return name.strip().lower() in GENERIC_INPUT_DEVICE_NAMES


def _can_open_input_device(index: int) -> bool:
    try:
        sd.check_input_settings(device=index, samplerate=SAMPLE_RATE, channels=CHANNELS)
    except Exception:
        return False
    return True


def list_selectable_input_devices() -> list[dict[str, object]]:
    devices = []
    seen_names: set[str] = set()
    for index, device in enumerate(sd.query_devices()):
        name = str(device["name"])
        if device["max_input_channels"] <= 0:
            continue
        if _is_generic_input_alias(name):
            continue
        if not _can_open_input_device(index):
            continue
        if name in seen_names:
            continue
        seen_names.add(name)
        devices.append(
            {
                "index": index,
                "name": name,
                "hostapi": device["hostapi"],
                "max_input_channels": device["max_input_channels"],
                "default_samplerate": device["default_samplerate"],
            }
        )
    return devices
```

- [ ] **Step 4: Update settings dialog to use selectable devices**

Change import:

```python
from speedytype.audio import list_selectable_input_devices
```

Change device list loop:

```python
for device in list_selectable_input_devices():
    name = str(device["name"])
    self._device_values.append(name)
    self.device_combo.addItem(name)
```

- [ ] **Step 5: Update settings dialog tests**

Change tests that assert raw sounddevice equivalence so they assert selectable behavior instead:

```python
def test_device_combo_lists_selectable_input_devices(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "speedytype.settings_dialog.list_selectable_input_devices",
        lambda: [{"name": "Usable USB Mic"}, {"name": "Built-in Microphone"}],
    )

    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")

    assert [
        dialog.device_combo.itemText(i)
        for i in range(dialog.device_combo.count())
    ] == [SYSTEM_DEFAULT_DEVICE_LABEL, "Usable USB Mic", "Built-in Microphone"]
```

- [ ] **Step 6: Verify raw CLI behavior remains diagnostic**

Run:

```powershell
python -m speedytype list-audio-devices
```

Expected: raw candidates still print, including generic aliases if PortAudio reports them.

- [ ] **Step 7: Verify tests**

Run:

```powershell
python -m pytest -q tests/test_audio_devices.py tests/test_settings_dialog.py::test_device_combo_lists_selectable_input_devices tests/test_settings_dialog.py::test_device_combo_preselects_saved_device tests/test_settings_dialog.py::test_save_persists_chosen_device_name
```

Expected: PASS.

## Task 3: Prevent Mouse-Wheel Combo Changes

**Files:**
- Modify: `speedytype/settings_dialog.py`
- Test: `tests/test_settings_dialog.py`

**Interfaces:**
- Produces: `NoWheelComboBox(QComboBox)` with `wheelEvent(self, event) -> None`
- Consumes: existing settings dialog combo boxes.

- [ ] **Step 1: Write failing no-wheel test**

Add:

```python
def test_device_combo_ignores_wheel_events(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "speedytype.settings_dialog.list_selectable_input_devices",
        lambda: [{"name": "Mic A"}, {"name": "Mic B"}],
    )
    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")
    dialog.device_combo.setCurrentIndex(1)

    class FakeWheelEvent:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    event = FakeWheelEvent()
    dialog.device_combo.wheelEvent(event)

    assert event.ignored is True
    assert dialog.device_combo.currentIndex() == 1
```

- [ ] **Step 2: Run test and verify failure**

Run:

```powershell
python -m pytest -q tests/test_settings_dialog.py::test_device_combo_ignores_wheel_events
```

Expected: FAIL because `QComboBox.wheelEvent` changes/handles the event.

- [ ] **Step 3: Implement no-wheel combo**

Add near settings-dialog UI helpers:

```python
class NoWheelComboBox(QComboBox):
    def wheelEvent(self, event) -> None:  # noqa: N802
        event.ignore()
```

Use it for recording mode and device combo:

```python
self.recording_mode_combo = NoWheelComboBox()
self.device_combo = NoWheelComboBox()
```

- [ ] **Step 4: Add recording-mode no-wheel coverage**

Add:

```python
def test_recording_mode_combo_ignores_wheel_events(qapp, tmp_path):
    dialog = SettingsDialog(make_config(), tmp_path / ".env", tmp_path / "settings.json")
    dialog.recording_mode_combo.setCurrentIndex(0)

    class FakeWheelEvent:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    event = FakeWheelEvent()
    dialog.recording_mode_combo.wheelEvent(event)

    assert event.ignored is True
    assert dialog.recording_mode_combo.currentIndex() == 0
```

- [ ] **Step 5: Verify**

Run:

```powershell
python -m pytest -q tests/test_settings_dialog.py::test_device_combo_ignores_wheel_events tests/test_settings_dialog.py::test_recording_mode_combo_ignores_wheel_events
```

Expected: PASS.

## Task 4: Recording Pill UI Verification

**Files:**
- Modify: `tests/test_overlay.py`
- Modify: `docs/current/user/MAC_SETUP.md`
- Modify: `docs/current/user/README.md`
- Modify: `docs/current/STATUS.md`
- Modify only if needed: `speedytype/overlay.py`

**Interfaces:**
- Consumes: existing `RecordingPill.show_recording`, `show_elapsed`, `show_countdown`, `show_auto_stopped`, `_show_processing_now`.
- Produces: automated render smoke coverage and macOS real-device checklist wording.

- [ ] **Step 1: Add render smoke test for all pill states**

Add to `tests/test_overlay.py`:

```python
@pytest.mark.parametrize(
    ("name", "action"),
    [
        ("recording_start", lambda pill: pill.show_recording()),
        ("recording_25min", lambda pill: pill.show_elapsed(1500)),
        ("countdown_60", lambda pill: pill.show_countdown(60)),
        ("countdown_0", lambda pill: pill.show_countdown(0)),
        ("auto_stopped", lambda pill: pill.show_auto_stopped()),
        ("processing", lambda pill: pill._show_processing_now()),
    ],
)
def test_recording_pill_states_render_nonblank(qapp, pill, name, action):
    action(pill)
    qapp.processEvents()

    image = pill.grab().toImage()
    assert not image.isNull(), name
    colors = {
        image.pixelColor(x, y).name()
        for x in range(0, image.width(), 8)
        for y in range(0, image.height(), 8)
    }
    assert len(colors) > 1, name
```

- [ ] **Step 2: Run test and verify current behavior**

Run:

```powershell
$env:QT_QPA_PLATFORM='offscreen'
python -m pytest -q tests/test_overlay.py
```

Expected: PASS. If it fails due to blank grab in offscreen mode, switch the assertion to direct `QImage(PILL_WIDTH, PILL_HEIGHT)` painting with `pill.render(painter)`.

- [ ] **Step 3: If visual bounds fail, adjust overlay minimally**

Only if tests or manual screenshots show text overlap, widen the pill conservatively:

```python
PILL_WIDTH = 240
```

Then rerun `tests/test_overlay.py`.

- [ ] **Step 4: Update macOS checklist**

Update `docs/current/user/MAC_SETUP.md` checklist to require:

```markdown
- [ ] In Hold mode, press and hold the configured hotkey for at least 5 seconds.
      Confirm the recording pill appears after debounce and shows elapsed `MM:SS`.
- [ ] In Toggle mode, press once to start and wait at least 5 seconds.
      Confirm the pill remains visible and elapsed time continues updating.
- [ ] Temporarily set the maximum recording time low for test only, then confirm the
      final countdown and pill-local automatic-stop warning are visible and not clipped.
```

- [ ] **Step 5: Update user README and status**

Update `docs/current/user/README.md` to state the long-recording pill shows elapsed time, countdown, and automatic-stop warning on both Windows and macOS. Update `docs/current/STATUS.md` to mark Windows automated/render smoke as covered and macOS real-device visual check as pending.

- [ ] **Step 6: Verify docs**

Run:

```powershell
python -m pytest -q tests/test_release_docs.py
```

Expected: PASS.

## Task 5: Full Regression and Manual Acceptance

**Files:**
- No source files unless previous task reveals a failure.

**Interfaces:**
- Consumes: all previous task outputs.
- Produces: release-ready evidence.

- [ ] **Step 1: Run focused tests**

Run:

```powershell
python -m pytest -q tests/test_platform_app.py tests/test_settings_launcher.py tests/test_audio_devices.py tests/test_settings_dialog.py tests/test_overlay.py tests/test_release_docs.py
```

Expected: PASS.

- [ ] **Step 2: Run broader suite with known clipboard flake isolated**

Run:

```powershell
python -m pytest -q --deselect=tests/test_settings_dialog.py::test_empty_masked_key_field_accepts_paste_without_reveal
python -m pytest -q tests/test_settings_dialog.py::test_empty_masked_key_field_accepts_paste_without_reveal
```

Expected: broad suite PASS with one deselected; isolated clipboard test PASS.

- [ ] **Step 3: Run compile check**

Run:

```powershell
python -m compileall -q speedytype scripts
```

Expected: no output and exit code 0.

- [ ] **Step 4: Manual Windows checks**

Run:

```powershell
python -m speedytype settings
```

Verify:

- Windows taskbar icon is SpeedyType, not Python document icon.
- Device selector contains system default and usable microphone choices, not generic aliases or unopenable WDM-KS endpoints.
- Scrolling the settings page while the mouse is over recording mode or device selector does not change the selected value.
- Recording pill states still display elapsed/countdown/auto-stop warning correctly when daemon is restarted on the new code.

- [ ] **Step 5: Manual macOS checks**

Run on a real Mac:

```zsh
speedytype settings
speedytype daemon
```

Verify:

- Standalone settings and daemon-opened settings do not show an unintended Python Dock icon.
- Device selector hides unopenable/generic devices while preserving system default.
- Trackpad scrolling over combo boxes does not change recording mode or device.
- Recording pill elapsed/countdown/auto-stop warning renders correctly with macOS fonts and display scaling.

- [ ] **Step 6: Commit**

Commit in small focused commits:

```powershell
git add speedytype/platform/app.py speedytype/platform/_windows_app.py speedytype/platform/_macos_app.py speedytype/settings_launcher.py tests/test_platform_app.py tests/test_settings_launcher.py
git commit -m "fix: set settings application identity"

git add speedytype/audio.py speedytype/settings_dialog.py tests/test_audio_devices.py tests/test_settings_dialog.py
git commit -m "fix: harden recording device picker"

git add tests/test_overlay.py docs/current/user/README.md docs/current/user/MAC_SETUP.md docs/current/STATUS.md docs/current/engineering/KNOWN_LIMITATIONS.md
git commit -m "test: cover recording pill display states"
```

## Self-Review

- Spec coverage: all four reported issues are covered for Windows and macOS. App identity is Task 1; device list filtering is Task 2; mouse-wheel protection is Task 3; recording pill UI verification is Task 4.
- Platform coverage: Tasks 1, 2, 3 are implemented as cross-platform behavior with platform-specific identity handling only where needed. Task 4 explicitly separates automated Qt checks from macOS real-device visual acceptance.
- Scope control: no changes to capture, hotkey debounce, transcription, FLAC/WAV upload, keyring, or cost logic.
- Risk: filtering by `check_input_settings` may hide a device that would work through PortAudio resampling at another sample rate. This is acceptable for the settings picker because SpeedyType records at `16000 Hz / mono`; raw CLI listing remains available for diagnosis.
