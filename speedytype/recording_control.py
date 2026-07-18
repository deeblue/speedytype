"""Thread-safe recording mode transition decisions."""

from enum import Enum, auto
from threading import Lock


class RecordingAction(Enum):
    BEGIN_START = auto()
    CONFIRM_START = auto()
    CANCEL_START = auto()
    BEGIN_STOP = auto()
    CANCEL_STOP = auto()
    STOP = auto()
    NONE = auto()


class RecordingPhase(Enum):
    IDLE = auto()
    PENDING_START = auto()
    RECORDING_UNARMED = auto()
    RECORDING_ARMED = auto()
    PENDING_STOP = auto()
    STOPPING = auto()
    PROCESSING = auto()


class RecordingControl:
    """Decide recording actions while serializing competing event sources."""

    def __init__(self, mode: str):
        self._mode = mode
        self._phase = RecordingPhase.IDLE
        self._lock = Lock()
        self._next_token = 1
        self._candidate_token: int | None = None
        self._active_token: int | None = None

    @property
    def phase(self) -> RecordingPhase:
        with self._lock:
            return self._phase

    def _new_candidate(self) -> int:
        token = self._next_token
        self._next_token += 1
        self._candidate_token = token
        return token

    def _invalidate_tokens(self) -> None:
        self._candidate_token = None
        self._active_token = None

    def begin_activation(self) -> tuple[RecordingAction, int | None]:
        with self._lock:
            if self._phase is RecordingPhase.IDLE:
                self._phase = RecordingPhase.PENDING_START
                return RecordingAction.BEGIN_START, self._new_candidate()

            if (
                self._mode == "toggle"
                and self._phase is RecordingPhase.RECORDING_ARMED
            ):
                self._phase = RecordingPhase.PENDING_STOP
                return RecordingAction.BEGIN_STOP, self._new_candidate()

            return RecordingAction.NONE, None

    def confirm_activation(self, token: int) -> RecordingAction:
        with self._lock:
            if token != self._candidate_token:
                return RecordingAction.NONE

            if self._phase is RecordingPhase.PENDING_START:
                self._candidate_token = None
                self._active_token = token
                self._phase = (
                    RecordingPhase.RECORDING_ARMED
                    if self._mode == "hold"
                    else RecordingPhase.RECORDING_UNARMED
                )
                return RecordingAction.CONFIRM_START

            if self._phase is RecordingPhase.PENDING_STOP:
                self._invalidate_tokens()
                self._phase = RecordingPhase.STOPPING
                return RecordingAction.STOP

            return RecordingAction.NONE

    def hotkey_released(self, token: int) -> RecordingAction:
        with self._lock:
            if (
                self._phase is RecordingPhase.PENDING_START
                and token == self._candidate_token
            ):
                self._invalidate_tokens()
                self._phase = RecordingPhase.IDLE
                return RecordingAction.CANCEL_START

            if (
                self._phase is RecordingPhase.PENDING_STOP
                and token == self._candidate_token
            ):
                self._candidate_token = None
                self._phase = RecordingPhase.RECORDING_ARMED
                return RecordingAction.CANCEL_STOP

            if (
                self._mode == "hold"
                and self._phase is RecordingPhase.RECORDING_ARMED
                and token == self._active_token
            ):
                self._invalidate_tokens()
                self._phase = RecordingPhase.STOPPING
                return RecordingAction.STOP

            if (
                self._mode == "toggle"
                and self._phase is RecordingPhase.RECORDING_UNARMED
                and token == self._active_token
            ):
                self._active_token = None
                self._phase = RecordingPhase.RECORDING_ARMED

            return RecordingAction.NONE

    def timeout(self) -> RecordingAction:
        with self._lock:
            if self._phase in (
                RecordingPhase.RECORDING_UNARMED,
                RecordingPhase.RECORDING_ARMED,
                RecordingPhase.PENDING_STOP,
            ):
                self._invalidate_tokens()
                self._phase = RecordingPhase.STOPPING
                return RecordingAction.STOP

            return RecordingAction.NONE

    def mark_processing(self) -> None:
        with self._lock:
            if self._phase is RecordingPhase.STOPPING:
                self._phase = RecordingPhase.PROCESSING

    def recording_failed(self) -> None:
        with self._lock:
            if self._phase in (
                RecordingPhase.PENDING_START,
                RecordingPhase.RECORDING_UNARMED,
                RecordingPhase.RECORDING_ARMED,
                RecordingPhase.PENDING_STOP,
                RecordingPhase.STOPPING,
            ):
                self._invalidate_tokens()
                self._phase = RecordingPhase.IDLE

    def processing_finished(self) -> None:
        with self._lock:
            if self._phase is RecordingPhase.PROCESSING:
                self._invalidate_tokens()
                self._phase = RecordingPhase.IDLE
