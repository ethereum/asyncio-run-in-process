import enum


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
    STOPPING = 6
    FINISHED = 7

    def is_next(self, other: "State") -> bool:
        return other == self + 1

    def is_on_or_after(self, other: "State") -> bool:
        return self >= other

    def is_before(self, other: "State") -> bool:
        return self < other
