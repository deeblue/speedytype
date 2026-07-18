from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from speedytype.recording_control import (
    RecordingAction,
    RecordingControl,
    RecordingPhase,
)


def _race(*events):
    barrier = Barrier(len(events))

    def run(event):
        barrier.wait()
        return event()

    with ThreadPoolExecutor(max_workers=len(events)) as executor:
        return list(executor.map(run, events))


def test_hold_activation_starts_armed_and_release_stops():
    control = RecordingControl("hold")

    assert control.activate() is RecordingAction.START
    assert control.phase is RecordingPhase.RECORDING_ARMED
    assert control.hotkey_released() is RecordingAction.STOP
    assert control.phase is RecordingPhase.STOPPING


def test_toggle_requires_release_before_second_activation_stops():
    control = RecordingControl("toggle")

    assert control.activate() is RecordingAction.START
    assert control.phase is RecordingPhase.RECORDING_UNARMED
    assert control.activate() is RecordingAction.NONE
    assert control.hotkey_released() is RecordingAction.NONE
    assert control.phase is RecordingPhase.RECORDING_ARMED
    assert control.activate() is RecordingAction.STOP
    assert control.timeout() is RecordingAction.NONE


def test_timeout_stops_exactly_once_in_each_mode():
    for mode in ("hold", "toggle"):
        control = RecordingControl(mode)
        control.activate()

        assert control.timeout() is RecordingAction.STOP
        assert control.timeout() is RecordingAction.NONE
        assert control.hotkey_released() is RecordingAction.NONE
        assert control.activate() is RecordingAction.NONE


def test_recording_failure_resets_to_idle_and_stale_events_are_ignored():
    control = RecordingControl("hold")
    control.activate()

    control.recording_failed()

    assert control.phase is RecordingPhase.IDLE
    assert control.hotkey_released() is RecordingAction.NONE
    assert control.timeout() is RecordingAction.NONE


def test_processing_ignores_recording_events_then_finishes_for_next_recording():
    control = RecordingControl("toggle")
    control.activate()
    control.timeout()

    control.mark_processing()

    assert control.phase is RecordingPhase.PROCESSING
    assert control.activate() is RecordingAction.NONE
    assert control.hotkey_released() is RecordingAction.NONE
    assert control.timeout() is RecordingAction.NONE

    control.processing_finished()

    assert control.phase is RecordingPhase.IDLE
    assert control.activate() is RecordingAction.START


def test_mark_processing_only_advances_from_stopping():
    control = RecordingControl("hold")

    control.mark_processing()
    assert control.phase is RecordingPhase.IDLE

    control.activate()
    control.mark_processing()
    assert control.phase is RecordingPhase.RECORDING_ARMED

    control.hotkey_released()
    control.mark_processing()
    assert control.phase is RecordingPhase.PROCESSING


def test_processing_finished_only_resets_processing():
    control = RecordingControl("hold")

    control.activate()
    control.processing_finished()

    assert control.phase is RecordingPhase.RECORDING_ARMED


def test_concurrent_activations_start_only_one_recording():
    control = RecordingControl("toggle")

    actions = _race(control.activate, control.activate)

    assert actions.count(RecordingAction.START) == 1
    assert actions.count(RecordingAction.NONE) == 1


def test_concurrent_stop_events_choose_exactly_one_winner():
    control = RecordingControl("hold")
    control.activate()

    actions = _race(control.hotkey_released, control.timeout)

    assert actions.count(RecordingAction.STOP) == 1
    assert actions.count(RecordingAction.NONE) == 1
    assert control.phase is RecordingPhase.STOPPING
