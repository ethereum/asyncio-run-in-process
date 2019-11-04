from abc import (
    ABC,
    abstractmethod,
)
import signal
from typing import (
    Generic,
    Optional,
)

from .state import (
    State,
)
from .typing import (
    TReturn,
)


class ProcessAPI(ABC, Generic[TReturn]):
    sub_proc_payload: bytes

    #
    # State
    #
    @property
    @abstractmethod
    def state(self) -> State:
        ...

    @abstractmethod
    async def update_state(self, value: State) -> None:
        ...

    @abstractmethod
    async def wait_for_state(self, state: State) -> None:
        ...

    #
    # PID
    #
    @property
    @abstractmethod
    def pid(self) -> int:
        ...

    @pid.setter
    def pid(self, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_pid(self) -> int:
        ...

    #
    # Return Value
    #
    @property
    @abstractmethod
    def return_value(self) -> TReturn:
        ...

    @return_value.setter
    def return_value(self, value: TReturn) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_return_value(self) -> TReturn:
        ...

    #
    # Return Code
    #
    @property
    @abstractmethod
    def returncode(self) -> int:
        ...

    @returncode.setter
    def returncode(self, value: int) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_returncode(self) -> int:
        ...

    #
    # Error
    #
    @property
    @abstractmethod
    def error(self) -> Optional[BaseException]:
        ...

    @error.setter
    def error(self, value: BaseException) -> None:
        raise NotImplementedError

    @abstractmethod
    async def wait_error(self) -> Optional[BaseException]:
        ...

    #
    # Result
    #
    @property
    @abstractmethod
    def result(self) -> TReturn:
        ...

    @abstractmethod
    async def wait_result(self) -> TReturn:
        ...

    #
    # Lifecycle management APIs
    #
    @abstractmethod
    async def wait(self) -> None:
        ...

    @abstractmethod
    async def kill(self) -> None:
        ...

    @abstractmethod
    def terminate(self) -> None:
        ...

    @abstractmethod
    def send_signal(self, sig: signal.Signals) -> None:
        ...
