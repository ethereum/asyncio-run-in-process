import asyncio
import io
import os
import sys
import traceback
from types import (
    TracebackType,
)
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    BinaryIO,
    Tuple,
    cast,
)

from async_generator import (
    asynccontextmanager,
)
import cloudpickle


def get_subprocess_command(
    child_r: int, child_w: int, parent_pid: int
) -> Tuple[str, ...]:
    from . import _child

    return (
        sys.executable,
        "-m",
        _child.__name__,
        "--parent-pid",
        str(parent_pid),
        "--fd-read",
        str(child_r),
        "--fd-write",
        str(child_w),
    )


def pickle_value(value: Any) -> bytes:
    serialized_value = cloudpickle.dumps(value)
    # mypy doesn't recognize that this line produces a bytes type.
    return len(serialized_value).to_bytes(4, 'big') + serialized_value  # type: ignore


def read_exactly(stream: BinaryIO, num_bytes: int) -> bytes:
    buffer = io.BytesIO()
    bytes_remaining = num_bytes
    while bytes_remaining > 0:
        data = stream.read(bytes_remaining)
        if data == b"":
            raise ConnectionError("Got end of stream")
        buffer.write(data)
        bytes_remaining -= len(data)

    return buffer.getvalue()


def receive_pickled_value(stream: BinaryIO) -> Any:
    len_bytes = read_exactly(stream, 4)
    serialized_len = int.from_bytes(len_bytes, "big")
    serialized_result = read_exactly(stream, serialized_len)
    return cloudpickle.loads(serialized_result)


class RemoteTraceback(Exception):

    def __init__(self, tb: str) -> None:
        self.tb = tb

    def __str__(self) -> str:
        return self.tb


class RemoteException(Exception):
    def __init__(self, exc: BaseException, tb: TracebackType) -> None:
        self.tb = (
            f'\n""" (exception from process: {os.getpid()})\n'
            f"{''.join(traceback.format_exception(type(exc), exc, tb))}"
            '"""'
        )
        self.exc = exc

    def __reduce__(self) -> Any:
        """
        Trick the `pickle` module into recreating this as the original
        exception when the value gets unpickled.
        """
        return rebuild_exc, (self.exc, self.tb)


def rebuild_exc(exc, tb):  # type: ignore
    exc.__cause__ = RemoteTraceback(tb)
    return exc


def cleanup_tasks(*tasks: 'asyncio.Future[Any]') -> AsyncContextManager[None]:
    """
    Context manager that ensures that all tasks are properly cancelled and awaited.

    The order in which tasks are cleaned is such that the first task will be
    the last to be cancelled/awaited.

    This function **must** be called with at least one task.
    """
    return cast(
        AsyncContextManager[None],
        _cleanup_tasks(*tasks),
    )


# mypy recognizes this decorator as being untyped.
@asynccontextmanager  # type: ignore
async def _cleanup_tasks(task: 'asyncio.Future[Any]',
                         *tasks: 'asyncio.Future[Any]',
                         ) -> AsyncIterator[None]:
    try:
        if tasks:
            async with cleanup_tasks(*tasks):
                yield
        else:
            yield
    finally:
        if not task.done():
            task.cancel()

        try:
            await task
        except asyncio.CancelledError:
            pass
