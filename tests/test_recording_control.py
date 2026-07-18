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


def _confirmed(control: RecordingControl) -> int:
    action, token = control.begin_activation()
    assert action is RecordingAction.BEGIN_START
    assert token is not None
    assert control.confirm_activation(token) is RecordingAction.CONFIRM_START
    return token


def test_hold_short_activation_is_pending_then_cancelled():
    control = RecordingControl("hold")

    action, token = control.begin_activation()

    assert action is RecordingAction.BEGIN_START
    assert token is not None
    assert control.phase is RecordingPhase.PENDING_START
    assert control.hotkey_released(token) is RecordingAction.CANCEL_START
    assert control.phase is RecordingPhase.IDLE


def test_hold_confirmed_activation_arms_and_release_stops():
    control = RecordingControl("hold")

    token = _confirmed(control)

    assert control.phase is RecordingPhase.RECORDING_ARMED
    assert control.hotkey_released(token) is RecordingAction.STOP
    assert control.phase is RecordingPhase.STOPPING


def test_toggle_short_start_cancels_and_confirmed_start_rearms_on_release():
    control = RecordingControl("toggle")
    action, short_token = control.begin_activation()

    assert action is RecordingAction.BEGIN_START
    assert control.hotkey_released(short_token) is RecordingAction.CANCEL_START

    token = _confirmed(control)
    assert control.phase is RecordingPhase.RECORDING_UNARMED
    assert control.hotkey_released(token) is RecordingAction.NONE
    assert control.phase is RecordingPhase.RECORDING_ARMED


def test_toggle_short_stop_is_cancelled_without_stopping_recording():
    control = RecordingControl("toggle")
    start_token = _confirmed(control)
    control.hotkey_released(start_token)

    action, stop_token = control.begin_activation()

    assert action is RecordingAction.BEGIN_STOP
    assert stop_token is not None
    assert control.phase is RecordingPhase.PENDING_STOP
    assert control.hotkey_released(stop_token) is RecordingAction.CANCEL_STOP
    assert control.phase is RecordingPhase.RECORDING_ARMED


def test_toggle_confirmed_stop_stops_exactly_once():
    control = RecordingControl("toggle")
    start_token = _confirmed(control)
    control.hotkey_released(start_token)
    action, stop_token = control.begin_activation()
    assert action is RecordingAction.BEGIN_STOP

    assert control.confirm_activation(stop_token) is RecordingAction.STOP
    assert control.confirm_activation(stop_token) is RecordingAction.NONE
    assert control.hotkey_released(stop_token) is RecordingAction.NONE
    assert control.phase is RecordingPhase.STOPPING


def test_duplicate_activation_while_pending_is_ignored():
    control = RecordingControl("hold")

    first = control.begin_activation()
    second = control.begin_activation()

    assert first[0] is RecordingAction.BEGIN_START
    assert second == (RecordingAction.NONE, None)


def test_timeout_invalidates_pending_stop_and_stale_token():
    control = RecordingControl("toggle")
    start_token = _confirmed(control)
    control.hotkey_released(start_token)
    _, stop_token = control.begin_activation()

    assert control.timeout() is RecordingAction.STOP
    assert control.confirm_activation(stop_token) is RecordingAction.NONE
    assert control.hotkey_released(stop_token) is RecordingAction.NONE
    assert control.phase is RecordingPhase.STOPPING


def test_stale_token_cannot_change_the_next_recording():
    control = RecordingControl("hold")
    _, stale = control.begin_activation()
    control.hotkey_released(stale)
    _, current = control.begin_activation()

    assert control.confirm_activation(stale) is RecordingAction.NONE
    assert control.hotkey_released(stale) is RecordingAction.NONE
    assert control.phase is RecordingPhase.PENDING_START
    assert control.confirm_activation(current) is RecordingAction.CONFIRM_START


def test_recording_failure_resets_pending_state_and_invalidates_token():
    control = RecordingControl("hold")
    _, token = control.begin_activation()

    control.recording_failed()

    assert control.phase is RecordingPhase.IDLE
    assert control.confirm_activation(token) is RecordingAction.NONE
    assert control.hotkey_released(token) is RecordingAction.NONE


def test_processing_ignores_events_then_finishes_for_next_recording():
    control = RecordingControl("toggle")
    _confirmed(control)
    control.timeout()
    control.mark_processing()

    assert control.phase is RecordingPhase.PROCESSING
    assert control.begin_activation() == (RecordingAction.NONE, None)
    assert control.timeout() is RecordingAction.NONE

    control.processing_finished()

    assert control.phase is RecordingPhase.IDLE
    assert control.begin_activation()[0] is RecordingAction.BEGIN_START


def test_release_and_timeout_race_has_one_stop_winner():
    control = RecordingControl("hold")
    token = _confirmed(control)

    actions = _race(lambda: control.hotkey_released(token), control.timeout)

    assert actions.count(RecordingAction.STOP) == 1
    assert actions.count(RecordingAction.NONE) == 1
    assert control.phase is RecordingPhase.STOPPING


def test_confirm_and_release_race_has_one_pending_start_winner():
    control = RecordingControl("hold")
    _, token = control.begin_activation()

    actions = _race(
        lambda: control.confirm_activation(token),
        lambda: control.hotkey_released(token),
    )

    assert set(actions) in (
        {RecordingAction.CONFIRM_START, RecordingAction.STOP},
        {RecordingAction.CANCEL_START, RecordingAction.NONE},
    )
