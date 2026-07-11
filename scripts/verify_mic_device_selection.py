from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import sounddevice as sd

from speedytype.audio import Recorder, list_input_devices, record_diagnostic
from speedytype.config import load_config, resolve_mic_device_setting
from speedytype.settings import AppSettings, save_settings


def main() -> int:
    print("=== 1. Device list accuracy ===")
    ui_devices = list_input_devices()
    raw_devices = [
        {"index": i, "name": str(d["name"])}
        for i, d in enumerate(sd.query_devices())
        if d["max_input_channels"] > 0
    ]
    ui_pairs = [(d["index"], d["name"]) for d in ui_devices]
    raw_pairs = [(d["index"], d["name"]) for d in raw_devices]
    print(f"UI list matches raw sounddevice query: {ui_pairs == raw_pairs}")
    for index, name in ui_pairs:
        print(f"  {index}: {name}")

    default_index = sd.default.device[0]
    print(f"\nSystem default input device index: {default_index}")

    non_default = next((d for d in ui_devices if d["index"] != default_index), None)
    if non_default is None:
        print("Only one input device on this machine; cannot test a non-default explicit selection.")
        return 1
    non_default_name = str(non_default["name"])
    non_default_index = non_default["index"]
    print(f"Chosen non-default device for this test: index={non_default_index} name={non_default_name!r}")

    print("\n=== 2. Recorder receives the correct device index ===")
    recorder_default = Recorder(device="")
    print(f"Recorder(device='').device = {recorder_default.device} (expect None -> sounddevice uses its own default, actual default index={default_index})")

    recorder_explicit = Recorder(device=non_default_name)
    print(f"Recorder(device={non_default_name!r}).device = {recorder_explicit.device} (expect {non_default_index})")
    explicit_ok = recorder_explicit.device == non_default_index

    print("\n=== 3. Real recording through the explicitly-selected device ===")
    diag_path = Path("scratch_device_selection_test.wav")
    result = record_diagnostic(diag_path, seconds=2.0, device=non_default_name)
    print(f"record_diagnostic result: {result}")
    diag_path.unlink(missing_ok=True)
    recording_ok = result["device_index"] == non_default_index and result["samples"] > 0

    print("\n=== 4. End-to-end via settings.json + load_config ===")
    tmp_dir = Path("scratch_device_settings_test")
    tmp_dir.mkdir(exist_ok=True)
    env_path = tmp_dir / ".env"
    env_path.write_text("OPENAI_API_KEY=x\nGEMINI_API_KEY=y\n", encoding="utf-8")
    settings_path = tmp_dir / "settings.json"

    save_settings(settings_path, AppSettings(mic_device_name=non_default_name))
    config = load_config(str(env_path), settings_path=str(settings_path))
    print(f"config.mic_device={config.mic_device!r} config.mic_device_warning={config.mic_device_warning!r}")
    recorder_from_config = Recorder(device=config.mic_device)
    print(f"Recorder built from config.mic_device -> .device = {recorder_from_config.device} (expect {non_default_index})")
    e2e_ok = config.mic_device == non_default_name and not config.mic_device_warning and recorder_from_config.device == non_default_index

    print("\n=== 5. Fallback when saved device is missing ===")
    save_settings(settings_path, AppSettings(mic_device_name="Totally Fake Missing Device 12345"))
    config2 = load_config(str(env_path), settings_path=str(settings_path))
    print(f"config2.mic_device={config2.mic_device!r} config2.mic_device_warning={config2.mic_device_warning!r}")
    recorder_fallback = Recorder(device=config2.mic_device)
    print(f"Recorder built from fallback config -> .device = {recorder_fallback.device} (expect None/default, no crash)")
    fallback_ok = config2.mic_device == "" and bool(config2.mic_device_warning)

    for path in (env_path, settings_path):
        path.unlink(missing_ok=True)
    tmp_dir.rmdir()

    print("\n=== SUMMARY ===")
    print(f"list_accuracy_ok={ui_pairs == raw_pairs}")
    print(f"explicit_device_index_ok={explicit_ok}")
    print(f"real_recording_ok={recording_ok}")
    print(f"end_to_end_ok={e2e_ok}")
    print(f"fallback_ok={fallback_ok}")
    all_ok = (ui_pairs == raw_pairs) and explicit_ok and recording_ok and e2e_ok and fallback_ok
    print(f"STATUS={'PASS' if all_ok else 'FAIL'}")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
