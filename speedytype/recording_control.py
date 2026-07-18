"""Thread-safe recording mode transition decisions."""

from enum import Enum, auto
from threading import Lock


class RecordingAction(Enum):
    START = auto()
    STOP = auto()
    NONE = auto()


class RecordingPhase(Enum):
    IDLE = auto()
    RECORDING_UNARMED = auto()
    RECORDING_ARMED = auto()
    STOPPING = auto()
    PROCESSING = auto()


class RecordingControl:
    """Decide recording actions while serializing competing event sources."""

    def __init__(self, mode: str):
        self._mode = mode
        self._phase = RecordingPhase.IDLE
        self._lock = Lock()

    @property
    def phase(self) -> RecordingPhase:
        with self._lock:
            return self._phase

    def activate(self) -> RecordingAction:
        with self._lock:
            if self._phase is RecordingPhase.IDLE:
                if self._mode == "hold":
                    self._phase = RecordingPhase.RECORDING_ARMED
                else:
                    self._phase = RecordingPhase.RECORDING_UNARMED
                return RecordingAction.START

            if (
                self._mode == "toggle"
                and self._phase is RecordingPhase.RECORDING_ARMED
            ):
                self._phase = RecordingPhase.STOPPING
                return RecordingAction.STOP

            return RecordingAction.NONE

    def hotkey_released(self) -> RecordingAction:
        with self._lock:
            if self._mode == "hold" and self._phase is RecordingPhase.RECORDING_ARMED:
                self._phase = RecordingPhase.STOPPING
                return RecordingAction.STOP

            if (
                self._mode == "toggle"
                and self._phase is RecordingPhase.RECORDING_UNARMED
            ):
                self._phase = RecordingPhase.RECORDING_ARMED

            return RecordingAction.NONE

    def timeout(self) -> RecordingAction:
        with self._lock:
            if self._phase in (
                RecordingPhase.RECORDING_UNARMED,
                RecordingPhase.RECORDING_ARMED,
            ):
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
                RecordingPhase.RECORDING_UNARMED,
                RecordingPhase.RECORDING_ARMED,
                RecordingPhase.STOPPING,
            ):
                self._phase = RecordingPhase.IDLE

    def processing_finished(self) -> None:
        with self._lock:
            if self._phase is RecordingPhase.PROCESSING:
                self._phase = RecordingPhase.IDLE
