import asyncio
import os
import signal
from typing import (
    Any,
    Callable,
    Optional,
    Sequence,
)

from ._utils import (
    pickle_value,
)
from .abc import (
    ProcessAPI,
)
from .exceptions import (
    ProcessKilled,
)
from .state import (
    State,
)
from .typing import (
    TReturn,
)


class Process(ProcessAPI[TReturn]):
    _pid: Optional[int] = None
    _returncode: Optional[int] = None
    _return_value: TReturn
    _error: Optional[BaseException] = None
    _state: State = State.INITIALIZING

    sub_proc_payload: bytes

    def __init__(
        self, async_fn: Callable[..., TReturn], args: Sequence[Any]
    ) -> None:
        self._async_fn = async_fn
        self._args = args
        self.sub_proc_payload = pickle_value((self._async_fn, self._args))

        self._has_pid = asyncio.Event()
        self._has_returncode = asyncio.Event()
        self._has_return_value = asyncio.Event()
        self._has_error = asyncio.Event()
        self._state_changed = asyncio.Condition()

    def __str__(self) -> str:
        return f"Process[{self._async_fn.__name__}]"

    #
    # State
    #
    @property
    def state(self) -> State:
        """
        Return the current state of the process.
        """
        return self._state

    async def update_state(self, state: State) -> None:
        """
        Update the state of the process.

        .. warning::

            This is an internal API and should not be used in user code.
        """
        async with self._state_changed:
            self._state = state
            self._state_changed.notify_all()

    async def wait_for_state(self, state: State) -> None:
        """
        Block until the process has reached or surpassed the given state.
        """
        if self.state.is_on_or_after(state):
            return

        # We use a loop since there should be a finite number of possible state
        # transitions and thus we should arrived at the desired state within a
        # number of iterations equal to that of the number of possible states.
        for _ in range(len(State)):
            async with self._state_changed:
                await self._state_changed.wait()
                if self.state.is_on_or_after(state):
                    break
        else:
            raise BaseException(
                f"This code path should not be reachable since there are a "
                f"finite number of state transitions.  Current state is "
                f"{self.state}"
            )

    #
    # PID
    #
    @property
    def pid(self) -> int:
        """
        Return the process id of the process

        Raises an `AttributeError` if the process id is not yet available.
        """
        if self._pid is None:
            raise AttributeError("No PID set for process")
        return self._pid

    @pid.setter
    def pid(self, value: int) -> None:
        self._pid = value
        self._has_pid.set()

    async def wait_pid(self) -> int:
        """
        Block until the process id is available.
        """
        await self._has_pid.wait()
        return self.pid

    #
    # Return Value
    #
    @property
    def return_value(self) -> TReturn:
        """
        Return the return value of the proc

        Raises an `AttributeError` if the process has not exited.
        """
        if not hasattr(self, "_return_value"):
            raise AttributeError("No return_value set")
        return self._return_value

    @return_value.setter
    def return_value(self, value: TReturn) -> None:
        self._return_value = value
        self._has_return_value.set()

    async def wait_return_value(self) -> TReturn:
        """
        Block until the return code of the process has been set.

        This will block indefinitely if the process exits with an error.
        """
        await self._has_return_value.wait()
        return self.return_value

    #
    # Return Code
    #
    @property
    def returncode(self) -> int:
        """
        Return the integer return code of the process.

        Raises an `AttributeError` if the process has not exited.
        """
        if self._returncode is None:
            raise AttributeError("No returncode set")
        return self._returncode

    @returncode.setter
    def returncode(self, value: int) -> None:
        self._returncode = value
        self._has_returncode.set()

    async def wait_returncode(self) -> int:
        """
        Block until the return code of the process has been set.
        """
        await self._has_returncode.wait()
        return self.returncode

    #
    # Error
    #
    @property
    def error(self) -> Optional[BaseException]:
        """
        Return the error raised by the process.

        Raises an `AttributeError` if the process has not raised an exception.
        """
        if self._error is None and not hasattr(self, "_return_value"):
            raise AttributeError("No error set")
        return self._error

    @error.setter
    def error(self, value: BaseException) -> None:
        self._error = value
        self._has_error.set()

    async def wait_error(self) -> BaseException:
        """
        Block until the process has an error.

        This will block indefinitely if the process does not throw an exception.
        """
        await self._has_error.wait()
        # mypy is unable to tell that `self.error` **must** be non-null in this
        # case.
        return self.error  # type: ignore

    #
    # Result
    #
    @property
    def result(self) -> TReturn:
        """
        Return the computed result from the process.

        If the process has not finished then raises an `AttributeError`

        If the process raised an exception, that exception is raised.

        Otherwise returns the result of the process.
        """
        if self._error is None and not hasattr(self, "_return_value"):
            raise AttributeError("Process not done")
        elif self._error is not None:
            raise self._error
        elif hasattr(self, "_return_value"):
            return self._return_value
        else:
            raise BaseException("Code path should be unreachable")

    async def wait_result(self) -> TReturn:
        """
        Block until the process has exited, either returning the return value
        if execution was successful, or raising an exception if it failed
        """
        await self.wait_returncode()

        if self.returncode == 0:
            return await self.wait_return_value()
        else:
            raise await self.wait_error()

    #
    # Lifecycle management APIs
    #
    async def wait(self) -> None:
        """
        Block until the process has exited.
        """
        await self.wait_returncode()

        if self.returncode == 0:
            await self.wait_return_value()
        else:
            await self.wait_error()

    async def kill(self) -> None:
        """
        Issue a `SIGKILL` signal to the process.

        This immediately transitions the process state to `FINISHED` and sets
        the error to `ProcessKilled`
        """
        self.send_signal(signal.SIGKILL)
        await self.update_state(State.FINISHED)
        self.error = ProcessKilled("Process terminated with SIGKILL")

    def terminate(self) -> None:
        """
        Issues a `SIGTERM` to the process.
        """
        self.send_signal(signal.SIGTERM)

    def send_signal(self, signum: signal.Signals) -> None:
        """
        Issues the provided signal to the process.
        """
        os.kill(self.pid, signum.value)
