from concurrent.futures import ThreadPoolExecutor
import json

from speedytype.hotkey_debounce import append_rejection_record


EXPECTED_FIELDS = {
    "timestamp_utc",
    "platform",
    "mode",
    "hotkey",
    "intent",
    "held_ms",
    "threshold_ms",
    "decision",
    "cleanup",
}


def _payload(line: str) -> dict[str, object]:
    prefix = "HOTKEY_DEBOUNCE "
    assert line.startswith(prefix)
    return json.loads(line.removeprefix(prefix))


def test_rejection_record_has_exact_privacy_safe_fields(tmp_path):
    log_path = tmp_path / "speedytype_daemon.log"

    append_rejection_record(
        log_path,
        platform="win32",
        mode="hold",
        hotkey="f9",
        intent="start",
        held_ms=24.3456,
        cleanup="removed",
    )

    payload = _payload(log_path.read_text(encoding="utf-8").strip())
    assert set(payload) == EXPECTED_FIELDS
    assert payload | {
        "timestamp_utc": payload["timestamp_utc"],
    } == {
        "timestamp_utc": payload["timestamp_utc"],
        "platform": "win32",
        "mode": "hold",
        "hotkey": "f9",
        "intent": "start",
        "held_ms": 24.346,
        "threshold_ms": 80,
        "decision": "rejected",
        "cleanup": "removed",
    }
    line = log_path.read_text(encoding="utf-8")
    assert "secret" not in line
    assert ".wav" not in line


def test_rejection_logging_is_best_effort(tmp_path):
    append_rejection_record(
        tmp_path / "missing" / "speedytype_daemon.log",
        platform="darwin",
        mode="toggle",
        hotkey="f9",
        intent="stop",
        held_ms=10,
        cleanup="not-applicable",
    )


def test_concurrent_rejections_append_complete_individual_lines(tmp_path):
    log_path = tmp_path / "speedytype_daemon.log"

    def append(index: int) -> None:
        append_rejection_record(
            log_path,
            platform="win32",
            mode="toggle",
            hotkey="f9",
            intent="stop",
            held_ms=float(index),
            cleanup="not-applicable",
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        list(executor.map(append, range(24)))

    lines = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 24
    assert {float(_payload(line)["held_ms"]) for line in lines} == set(map(float, range(24)))
