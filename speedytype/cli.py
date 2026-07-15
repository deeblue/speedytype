from __future__ import annotations

import argparse
from pathlib import Path
import sys
import threading

from speedytype.api import discover_flash_model
from speedytype.audio import Recorder, list_input_devices, record_diagnostic, temp_wav_path
from speedytype.autostart import install_autostart, uninstall_autostart
from speedytype.command_alias import install_command_alias
from speedytype.config import ConfigError, load_config
from speedytype.daemon import run_daemon, stop_daemon
from speedytype.hotkey import register_hold_hotkey, remove_hotkey, wait_until_hotkey_released
from speedytype.pipeline import process_wav
from speedytype.paths import default_env_path
from speedytype.real_voice import guided_recording, validate_real_voice
from speedytype.settings_launcher import show_settings_dialog
from speedytype.version import VERSION


def _load_config_or_print(path: str):
    try:
        return load_config(path)
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        return None


def command_diagnose_config(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    print(
        "Config OK. "
        f"HOTKEY={config.hotkey}, "
        f"MIC_DEVICE={config.mic_device or 'default'}, "
        f"GEMINI_MODEL={config.gemini_model}, "
        f"LLM_PROVIDER={config.llm_provider}, "
        f"LLM_MODEL={config.llm_model}, "
        f"LLM_THINKING_LEVEL={config.llm_thinking_level or '-'}, "
        f"LLM_DISAMBIGUATION_HINTS={config.llm_disambiguation_hints}, "
        f"MAX_RECORD_SECONDS={config.max_record_seconds}, "
        f"LATENCY_LOG_PATH={config.latency_log_path}"
    )
    return 0


def command_discover_gemini_model(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    try:
        model = discover_flash_model(config.gemini_api_key)
    except Exception as exc:
        print(f"Gemini model discovery failed: {exc}", file=sys.stderr)
        return 1
    print(f"Selected Gemini Flash model: {model}")
    return 0


def command_run_once(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    try:
        process_wav(Path(args.wav), config, do_paste=not args.no_paste, usage_scope="daily")
    except Exception as exc:
        print(f"Pipeline failed: {exc}", file=sys.stderr)
        return 1
    return 0


def command_listen(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2

    recorder = Recorder(device=config.mic_device)
    active_thread: threading.Thread | None = None
    stop_thread: threading.Thread | None = None
    active_path: Path | None = None

    def on_press():
        nonlocal active_thread, stop_thread, active_path
        if active_thread and active_thread.is_alive():
            return
        active_path = temp_wav_path()
        print("Recording...", flush=True)
        active_thread = threading.Thread(target=recorder.record_until_stop, args=(active_path,), daemon=False)
        active_thread.start()
        stop_thread = threading.Thread(target=finish_recording_after_release, daemon=True)
        stop_thread.start()

    def finish_recording_after_release():
        nonlocal active_thread, active_path
        reason, elapsed = wait_until_hotkey_released(config.hotkey, config.max_record_seconds)
        if not active_thread or not active_thread.is_alive() or active_path is None:
            return
        if reason == "timeout":
            print(f"Recording timed out after {elapsed:.1f}s; stopping automatically.", flush=True)
        print("Processing...", flush=True)
        recorder.stop()
        active_thread.join()
        process_wav(active_path, config, do_paste=True, usage_scope="daily")

    hotkey_handle = register_hold_hotkey(config.hotkey, on_press)
    print(f"SpeedyType listening. Hold {config.hotkey.upper()} to record. Press Ctrl+C to exit.", flush=True)
    try:
        threading.Event().wait()
    except KeyboardInterrupt:
        print("Exiting.", flush=True)
    finally:
        remove_hotkey(hotkey_handle)
    return 0


def command_daemon(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    return run_daemon(config, env_path=args.env)


def command_daemon_stop(args: argparse.Namespace) -> int:
    ok, message = stop_daemon()
    print(message)
    return 0 if ok else 1


def command_settings(args: argparse.Namespace) -> int:
    return show_settings_dialog(args.env)


def command_install_command(args: argparse.Namespace) -> int:
    ok, message = install_command_alias(env_path=args.env)
    print(message)
    return 0 if ok else 1


def command_install_autostart(args: argparse.Namespace) -> int:
    ok, message = install_autostart(env_path=args.env)
    print(message)
    return 0 if ok else 1


def command_uninstall_autostart(args: argparse.Namespace) -> int:
    ok, message = uninstall_autostart()
    print(message)
    return 0 if ok else 1


def command_list_audio_devices(args: argparse.Namespace) -> int:
    devices = list_input_devices()
    for device in devices:
        print(
            f"{device['index']}: {device['name']} "
            f"(max_input_channels={device['max_input_channels']}, default_samplerate={device['default_samplerate']})"
        )
    return 0


def command_diagnose_audio(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    try:
        result = record_diagnostic(Path(args.output), seconds=args.seconds, device=config.mic_device)
    except Exception as exc:
        print(f"Audio diagnostic failed: {exc}", file=sys.stderr)
        return 1
    print(
        f"Audio diagnostic OK. device_index={result['device_index']} seconds={result['seconds']} "
        f"samples={result['samples']} rms={result['rms']:.6f} peak={result['peak']:.6f} path={result['path']}"
    )
    return 0


def command_guided_recording(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    guided_recording(
        Path(args.script),
        Path(args.output_dir),
        hotkey=config.hotkey,
        mic_device=config.mic_device,
        max_record_seconds=config.max_record_seconds,
    )
    return 0


def command_validate_real_voice(args: argparse.Namespace) -> int:
    config = _load_config_or_print(args.env)
    if config is None:
        return 2
    try:
        validate_real_voice(Path(args.dir), Path(args.script), config, Path(args.report))
    except Exception as exc:
        print(f"Real voice validation failed: {exc}", file=sys.stderr)
        return 1
    print(f"Real voice report written: {args.report}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="speedytype", description="SpeedyType Windows voice input POC")
    parser.add_argument(
        "--version",
        action="version",
        version=f"SpeedyType {VERSION}",
    )
    parser.add_argument("--env", default=str(default_env_path()), help="Path to .env config file")
    sub = parser.add_subparsers(dest="command", required=True)

    diagnose = sub.add_parser("diagnose-config")
    diagnose.set_defaults(func=command_diagnose_config)

    discover = sub.add_parser("discover-gemini-model")
    discover.set_defaults(func=command_discover_gemini_model)

    run_once = sub.add_parser("run-once")
    run_once.add_argument("wav")
    run_once.add_argument("--no-paste", action="store_true")
    run_once.set_defaults(func=command_run_once)

    listen = sub.add_parser("listen")
    listen.set_defaults(func=command_listen)

    daemon = sub.add_parser("daemon")
    daemon.set_defaults(func=command_daemon)

    daemon_stop = sub.add_parser("daemon-stop")
    daemon_stop.set_defaults(func=command_daemon_stop)

    settings_command = sub.add_parser("settings")
    settings_command.set_defaults(func=command_settings)

    install_command = sub.add_parser("install-command")
    install_command.set_defaults(func=command_install_command)

    install_auto = sub.add_parser("install-autostart")
    install_auto.set_defaults(func=command_install_autostart)

    uninstall_auto = sub.add_parser("uninstall-autostart")
    uninstall_auto.set_defaults(func=command_uninstall_autostart)

    list_audio = sub.add_parser("list-audio-devices")
    list_audio.set_defaults(func=command_list_audio_devices)

    diagnose_audio = sub.add_parser("diagnose-audio")
    diagnose_audio.add_argument("--output", default="audio_diagnostic.wav")
    diagnose_audio.add_argument("--seconds", type=float, default=2.0)
    diagnose_audio.set_defaults(func=command_diagnose_audio)

    guided = sub.add_parser("guided-recording")
    guided.add_argument("--script", default="real_voice_script.md")
    guided.add_argument("--output-dir", default="real_voice")
    guided.set_defaults(func=command_guided_recording)

    validate = sub.add_parser("validate-real-voice")
    validate.add_argument("--dir", default="real_voice")
    validate.add_argument("--script", default="real_voice_script.md")
    validate.add_argument("--report", default="REAL_VOICE_REPORT.md")
    validate.set_defaults(func=command_validate_real_voice)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)
