import signal
import sys
from typing import (
    Any,
    AsyncIterator,
    Awaitable,
    BinaryIO,
    Callable,
    Sequence,
)

import trio
import trio_typing

from ._utils import (
    RemoteException,
    pickle_value,
)
from .abc import (
    TAsyncFn,
)
from .state import (
    State,
    update_state,
    update_state_finished,
)
from .typing import (
    TReturn,
)

SHUTDOWN_SIGNALS = {signal.SIGTERM}


async def _do_monitor_signals(signal_aiter: AsyncIterator[int]) -> None:
    async for signum in signal_aiter:
        raise SystemExit(signum)


@trio_typing.takes_callable_and_args
async def _do_async_fn(
    async_fn: Callable[..., Awaitable[TReturn]],
    args: Sequence[Any],
    to_parent: BinaryIO,
) -> TReturn:
    with trio.open_signal_receiver(*SHUTDOWN_SIGNALS) as signal_aiter:
        # state: STARTED
        update_state(to_parent, State.STARTED)

        async with trio.open_nursery() as nursery:
            nursery.start_soon(_do_monitor_signals, signal_aiter)

            # state: EXECUTING
            update_state(to_parent, State.EXECUTING)

            result = await async_fn(*args)

            nursery.cancel_scope.cancel()
        return result


def _run_on_trio(async_fn: TAsyncFn, args: Sequence[Any], to_parent: BinaryIO) -> None:
    try:
        result = trio.run(_do_async_fn, async_fn, args, to_parent)
    except BaseException:
        _, exc_value, exc_tb = sys.exc_info()
        # `mypy` thinks that `exc_value` and `exc_tb` are `Optional[..]` types
        remote_exc = RemoteException(exc_value, exc_tb)  # type: ignore
        finished_payload = pickle_value(remote_exc)
        raise
    else:
        finished_payload = pickle_value(result)
    finally:
        update_state_finished(to_parent, finished_payload)


if __name__ == "__main__":
    from asyncio_run_in_process._child import parser, run_process
    args = parser.parse_args()
    run_process(
        runner=_run_on_trio,
        fd_read=args.fd_read,
        fd_write=args.fd_write,
    )
