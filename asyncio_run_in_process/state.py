import enum
import os
from typing import (
    BinaryIO,
)


class State(enum.IntEnum):
    """
    Child process lifecycle
    """

    INITIALIZING = 0
    INITIALIZED = 1
    WAIT_EXEC_DATA = 2
    BOOTING = 3
    STARTED = 4
    EXECUTING = 5
    FINISHED = 6

    def is_next(self, other: "State") -> bool:
        return other == self + 1

    def is_on_or_after(self, other: "State") -> bool:
        return self >= other

    def is_before(self, other: "State") -> bool:
        return self < other


def update_state(to_parent: BinaryIO, state: State) -> None:
    to_parent.write(state.value.to_bytes(1, 'big'))
    to_parent.flush()


def update_state_initialized(to_parent: BinaryIO) -> None:
    payload = State.INITIALIZED.value.to_bytes(1, 'big') + os.getpid().to_bytes(4, 'big')
    to_parent.write(payload)
    to_parent.flush()


def update_state_finished(to_parent: BinaryIO, finished_payload: bytes) -> None:
    payload = State.FINISHED.value.to_bytes(1, 'big') + finished_payload
    to_parent.write(payload)
    to_parent.flush()
