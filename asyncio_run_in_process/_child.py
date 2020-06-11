import argparse
import asyncio
import logging
import os
import signal
import sys
from typing import (
    Any,
    BinaryIO,
    Coroutine,
    Sequence,
    cast,
)

from ._utils import (
    RemoteException,
    cleanup_tasks,
    pickle_value,
    receive_pickled_value,
)
from .abc import (
    TAsyncFn,
    TEngineRunner,
)
from .exceptions import (
    ChildCancelled,
)
from .state import (
    State,
    update_state,
    update_state_finished,
    update_state_initialized,
)
from .typing import (
    TReturn,
)

logger = logging.getLogger("asyncio_run_in_process")


SHUTDOWN_SIGNALS = {signal.SIGTERM}


async def _handle_coro(coro: Coroutine[Any, Any, TReturn], got_SIGINT: asyncio.Event) -> TReturn:
    """
    Understanding this function requires some detailed knowledge of how
    coroutines work.

    The goal here is to run a coroutine function and wait for the result.
    However, if a SIGINT signal is received then we want to inject a
    `KeyboardInterrupt` exception into the running coroutine.

    Some additional nuance:

    - The `SIGINT` signal can happen multiple times and each time we want to
      throw a `KeyboardInterrupt` into the running coroutine which may choose to
      ignore the exception and continue executing.
    - When the `KeyboardInterrupt` hits the coroutine it can return a value
      which is sent using a `StopIteration` exception.  We treat this as the
      return value of the coroutine.
    """
    # The `coro` is first wrapped in `asyncio.shield` to protect us in the case
    # that a SIGINT happens.  In this case, the coro has a chance to return a
    # value during exception handling, in which case we are left with
    # `coro_task` which has not been awaited and thus will cause asyncio to
    # issue a warning.  However, since the coroutine has already exited, if we
    # await the `coro_task` then we will encounter a `RuntimeError`.  By
    # wrapping the coroutine in `asyncio.shield` we side-step this by
    # preventing the cancellation to actually penetrate the coroutine, allowing
    # us to await the `coro_task` without causing the `RuntimeError`.
    coro_task = asyncio.ensure_future(asyncio.shield(coro))
    async with cleanup_tasks(coro_task):
        while True:
            # Run the coroutine until it either returns, or a SIGINT is received.
            # This is done in a loop because the function *could* choose to ignore
            # the `KeyboardInterrupt` and continue processing, in which case we
            # reset the signal and resume waiting.
            done, pending = await asyncio.wait(
                (coro_task, got_SIGINT.wait()),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if coro_task.done():
                async with cleanup_tasks(*done, *pending):
                    return await coro_task
            elif got_SIGINT.is_set():
                got_SIGINT.clear()

                # In the event that a SIGINT was recieve we need to inject a
                # KeyboardInterrupt exception into the running coroutine.
                try:
                    coro.throw(KeyboardInterrupt)
                except StopIteration as err:
                    # StopIteration is how coroutines signal their return values.
                    # If the exception was raised, we treat the argument as the
                    # return value of the function.
                    async with cleanup_tasks(*done, *pending):
                        return cast(TReturn, err.value)
                except BaseException:
                    raise
            else:
                raise Exception("Code path should not be reachable")


async def _do_async_fn(
    async_fn: TAsyncFn,
    args: Sequence[Any],
    to_parent: BinaryIO,
    loop: asyncio.AbstractEventLoop,
) -> TReturn:
    # state: STARTED
    update_state(to_parent, State.STARTED)

    # A Future that will be set if any of the SHUTDOWN_SIGNALS signals are
    # received causing _do_async_fn to raise a SystemExit
    system_exit_signum: 'asyncio.Future[int]' = asyncio.Future()

    # setup signal handlers.
    for signum in SHUTDOWN_SIGNALS:
        loop.add_signal_handler(
            signum.value,
            system_exit_signum.set_result,
            signum,
        )

    # Install a signal handler to set an asyncio.Event upon receiving a SIGINT
    got_SIGINT = asyncio.Event()
    loop.add_signal_handler(
        signal.SIGINT,
        got_SIGINT.set,
    )

    # state: EXECUTING
    update_state(to_parent, State.EXECUTING)

    # First we need to generate a coroutine.  We need this so we can throw
    # exceptions into the running coroutine to allow it to handle keyboard
    # interrupts.
    async_fn_coro: Coroutine[Any, Any, TReturn] = async_fn(*args)

    # The coroutine is then given to `_handle_coro` which waits for either the
    # coroutine to finish, returning the result, or for a SIGINT signal at
    # which point injects a `KeyboardInterrupt` into the running coroutine.
    async_fn_task: 'asyncio.Future[TReturn]' = asyncio.ensure_future(
        _handle_coro(async_fn_coro, got_SIGINT),
    )

    # Now we wait for either a result from the coroutine or a SIGTERM which
    # triggers immediate cancellation of the running coroutine.
    done, pending = await asyncio.wait(
        (async_fn_task, system_exit_signum),
        return_when=asyncio.FIRST_COMPLETED,
    )

    # We prioritize the `SystemExit` case.
    async with cleanup_tasks(*done, *pending):
        if system_exit_signum.done():
            raise SystemExit(await system_exit_signum)
        elif async_fn_task.done():
            return await async_fn_task
        else:
            raise Exception("unreachable")


def _run_on_asyncio(async_fn: TAsyncFn, args: Sequence[Any], to_parent: BinaryIO) -> None:
    loop = asyncio.get_event_loop()
    try:
        result: Any = loop.run_until_complete(_do_async_fn(async_fn, args, to_parent, loop))
    except BaseException:
        exc_type, exc_value, exc_tb = sys.exc_info()
        # `mypy` thinks that `exc_value` and `exc_tb` are `Optional[..]` types
        if exc_type is asyncio.CancelledError:
            exc_value = ChildCancelled(*exc_value.args)  # type: ignore
        remote_exc = RemoteException(exc_value, exc_tb)  # type: ignore
        finished_payload = pickle_value(remote_exc)
        raise
    else:
        finished_payload = pickle_value(result)
    finally:
        update_state_finished(to_parent, finished_payload)


def run_process(runner: TEngineRunner, fd_read: int, fd_write: int) -> None:
    """
    Run the child process.

    This communicates the status of the child process back to the parent
    process over the given file descriptor, runs the coroutine, handles error
    cases, and transmits the result back to the parent process.
    """
    # state: INITIALIZING (default initial state)
    with os.fdopen(fd_write, "wb") as to_parent:
        # state: INITIALIZED
        update_state_initialized(to_parent)

        with os.fdopen(fd_read, "rb", closefd=True) as from_parent:
            # state: WAIT_EXEC_DATA
            update_state(to_parent, State.WAIT_EXEC_DATA)
            async_fn, args = receive_pickled_value(from_parent)

        # state: BOOTING
        update_state(to_parent, State.BOOTING)

        try:
            runner(async_fn, args, to_parent)
        except KeyboardInterrupt:
            code = 2
        except SystemExit as err:
            code = err.args[0]
        except BaseException:
            logger.exception("%s raised an unexpected exception", async_fn)
            code = 1
        else:
            code = 0
        finally:
            sys.exit(code)


#
# CLI invocation for subprocesses
#
parser = argparse.ArgumentParser(description="asyncio-run-in-process")
parser.add_argument(
    "--fd-read",
    type=int,
    required=True,
    help=(
        "The file descriptor that the child process can use to read data that "
        "has been written by the parent process"
    ),
)
parser.add_argument(
    "--fd-write",
    type=int,
    required=True,
    help=(
        "The file descriptor that the child process can use for writing data "
        "meant to be read by the parent process"
    ),
)


if __name__ == "__main__":
    args = parser.parse_args()
    run_process(
        runner=_run_on_asyncio,
        fd_read=args.fd_read,
        fd_write=args.fd_write,
    )
