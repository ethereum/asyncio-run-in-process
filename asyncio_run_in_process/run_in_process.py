import asyncio
import logging
import os
import signal
import sys
from typing import (
    TYPE_CHECKING,
    Any,
    AsyncContextManager,
    AsyncIterator,
    Callable,
    Optional,
    cast,
)

from async_generator import (
    asynccontextmanager,
)

from . import (
    constants,
)
from ._utils import (
    cleanup_tasks,
    get_subprocess_command,
    read_exactly,
    receive_pickled_value,
)
from .abc import (
    ProcessAPI,
)
from .exceptions import (
    InvalidState,
)
from .process import (
    Process,
)
from .state import (
    State,
)
from .typing import (
    TReturn,
)

if TYPE_CHECKING:
    from typing import Tuple  # noqa: F401
    from .typing import SubprocessKwargs  # noqa: F401


logger = logging.getLogger("asyncio_run_in_process")


async def _monitor_sub_proc(
    proc: ProcessAPI[TReturn], sub_proc: asyncio.subprocess.Process, parent_w: int
) -> None:
    logger.debug("starting subprocess to run %s", proc)

    await proc.wait_pid()
    if proc.pid != sub_proc.pid:
        raise Exception("Process id mismatch.  This should not be possible")
    logger.debug("subprocess for %s started.  pid=%d", proc, sub_proc.pid)

    # we write the execution data immediately without waiting for the
    # `WAIT_EXEC_DATA` state to ensure that the child process doesn't have
    # to wait for that data due to the round trip times between processes.
    logger.debug("writing execution data for %s over fd=%d", proc, parent_w)
    # pass the child process the serialized `async_fn` and `args`

    with os.fdopen(parent_w, "wb") as to_child:
        to_child.write(proc.sub_proc_payload)
        to_child.flush()

    await proc.wait_for_state(State.WAIT_EXEC_DATA)
    logger.debug("child process %s (pid=%d) waiting for exec data", proc, sub_proc.pid)

    await proc.wait_for_state(State.STARTED)
    logger.debug("waiting for process %s (pid=%d) to finish", proc, sub_proc.pid)

    await sub_proc.wait()

    proc.returncode = sub_proc.returncode
    logger.debug("process %s (pid=%d) finished: returncode=%d", proc, sub_proc.pid, proc.returncode)


async def _relay_signals(
    proc: ProcessAPI[Any],
    queue: 'asyncio.Queue[signal.Signals]',
) -> None:
    if proc.state.is_before(State.EXECUTING):
        # If the process has not reached the state where the child process
        # can properly handle the signal, give it a moment to reach the
        # `EXECUTING` stage.
        await proc.wait_for_state(State.EXECUTING)
    elif proc.state.is_on_or_after(State.STOPPING):
        await proc.wait_for_state(State.FINISHED)
        return

    while True:
        signum = await queue.get()

        logger.debug("relaying signal %s to child process %s", signum, proc)
        proc.send_signal(signum)


async def _monitor_state(
    proc: ProcessAPI[TReturn], parent_read_fd: int, loop: asyncio.AbstractEventLoop,
) -> None:
    with os.fdopen(parent_read_fd, "rb", closefd=True) as from_child:
        for expected_state in State:
            if proc.state is not expected_state:
                raise InvalidState(
                    f"Process in state {proc.state} but expected state {expected_state}"
                )

            next_expected_state = State(proc.state + 1)
            logger.debug(
                "Waiting for next expected state (%s) from child (%s)", next_expected_state, proc)
            child_state_as_byte = await loop.run_in_executor(None, read_exactly, from_child, 1)

            try:
                child_state = State(ord(child_state_as_byte))
            except TypeError:
                raise InvalidState(f"Child sent state: {child_state_as_byte.hex()}")

            if not proc.state.is_next(child_state):
                if proc.state is State.FINISHED:
                    # This case covers when the process is killed with a SIGKILL
                    # and jumps directly to the finished state.
                    return
                raise InvalidState(
                    f"Invalid state transition: {proc.state} -> {child_state}"
                )

            if child_state is State.FINISHED:
                # For the FINISHED state we delay updating the state until we also
                # have a return value.
                break
            elif child_state is State.INITIALIZED:
                # For the INITIALIZED state we expect an additional payload of the
                # process id.  The process ID is gotten via this mechanism to
                # prevent the need for ugly sleep based code in
                # `_monitor_sub_proc`.
                pid_bytes = await loop.run_in_executor(None, read_exactly, from_child, 4)
                proc.pid = int.from_bytes(pid_bytes, 'big')

            await proc.update_state(child_state)
            logger.debug(
                "Updated process %s state %s -> %s",
                proc,
                expected_state.name,
                child_state.name,
            )

        # This is mostly a sanity check but it ensures that the loop variable is
        # what we expect it to be before starting to collect the result the stream.
        if child_state is not State.FINISHED:
            raise InvalidState(f"Invalid final state: {proc.state}")

        result = await loop.run_in_executor(None, receive_pickled_value, from_child)

    await proc.wait_returncode()

    if proc.returncode == 0:
        proc.return_value = result
    else:
        proc.error = result

    await proc.update_state(child_state)
    logger.debug(
        "Updated process %s state %s -> %s",
        proc,
        expected_state.name,
        child_state.name,
    )


# SIGINT isn't included here because it's handled by catching the
# `KeyboardInterrupt` exception.
RELAY_SIGNALS = (signal.SIGTERM, signal.SIGHUP)


def open_in_process(
    async_fn: Callable[..., TReturn],
    *args: Any,
    loop: asyncio.AbstractEventLoop = None,
    subprocess_kwargs: 'SubprocessKwargs' = None,
) -> AsyncContextManager[ProcessAPI[TReturn]]:
    return cast(
        AsyncContextManager[ProcessAPI[TReturn]],
        _open_in_process(async_fn, *args, loop=loop, subprocess_kwargs=subprocess_kwargs),
    )


def _update_subprocess_kwargs(subprocess_kwargs: Optional['SubprocessKwargs'],
                              child_r: int,
                              child_w: int) -> 'SubprocessKwargs':
    if subprocess_kwargs is None:
        subprocess_kwargs = {}

    base_pass_fds = subprocess_kwargs.get('pass_fds', ())
    pass_fds: Tuple[int, ...]

    if base_pass_fds is None:
        pass_fds = (child_r, child_w)
    else:
        pass_fds = tuple(set(base_pass_fds).union((child_r, child_w)))

    updated_kwargs = subprocess_kwargs.copy()
    updated_kwargs['pass_fds'] = pass_fds

    return updated_kwargs


# mypy recognizes this decorator as being untyped.
@asynccontextmanager  # type: ignore
async def _open_in_process(
    async_fn: Callable[..., TReturn],
    *args: Any,
    loop: asyncio.AbstractEventLoop = None,
    subprocess_kwargs: 'SubprocessKwargs' = None,
) -> AsyncIterator[ProcessAPI[TReturn]]:
    proc: Process[TReturn] = Process(async_fn, args)

    parent_r, child_w = os.pipe()
    child_r, parent_w = os.pipe()
    parent_pid = os.getpid()

    command = get_subprocess_command(child_r, child_w, parent_pid)

    sub_proc = await asyncio.create_subprocess_exec(
        *command,
        **_update_subprocess_kwargs(subprocess_kwargs, child_r, child_w),
    )
    if loop is None:
        loop = asyncio.get_event_loop()

    signal_queue: asyncio.Queue[signal.Signals] = asyncio.Queue()

    for signum in RELAY_SIGNALS:
        loop.add_signal_handler(
            signum,
            signal_queue.put_nowait,
            signum,
        )

    # Monitoring
    monitor_sub_proc_task = asyncio.ensure_future(_monitor_sub_proc(proc, sub_proc, parent_w))
    relay_signals_task = asyncio.ensure_future(_relay_signals(proc, signal_queue))
    monitor_state_task = asyncio.ensure_future(_monitor_state(proc, parent_r, loop))

    async with cleanup_tasks(monitor_sub_proc_task, relay_signals_task, monitor_state_task):
        await proc.wait_pid()

        # Wait until the child process has reached the STARTED
        # state before yielding the context.  This ensures that any
        # calls to things like `terminate` or `kill` will be handled
        # properly in the child process.
        #
        # The timeout ensures that if something is fundamentally wrong
        # with the subprocess we don't hang indefinitely.
        await proc.wait_for_state(State.STARTED)

        try:
            try:
                yield proc
            except KeyboardInterrupt as err:
                # If a keyboard interrupt is encountered relay it to the
                # child process and then give it a moment to cleanup before
                # re-raising
                logger.debug("Relaying SIGINT to pid=%d", sub_proc.pid)
                try:
                    proc.send_signal(signal.SIGINT)
                    try:
                        await asyncio.wait_for(
                            proc.wait(), timeout=constants.SIGINT_TIMEOUT_SECONDS)
                    except asyncio.TimeoutError:
                        logger.debug(
                            "Timed out waiting for pid=%d to exit after relaying SIGINT",
                            sub_proc.pid,
                        )
                except BaseException:
                    logger.exception(
                        "Unexpected error when terminating child; pid=%d", sub_proc.pid)
                finally:
                    raise err
            except asyncio.CancelledError as err:
                # Send the child a SIGINT and wait SIGINT_TIMEOUT_SECONDS for it to terminate. If
                # that times out, send a SIGTERM and wait SIGTERM_TIMEOUT_SECONDS before
                # re-raising.
                logger.debug(
                    "Got CancelledError while running subprocess pid=%d.  Sending SIGINT.",
                    sub_proc.pid,
                )
                try:
                    proc.send_signal(signal.SIGINT)
                    try:
                        await asyncio.wait_for(
                            proc.wait(), timeout=constants.SIGINT_TIMEOUT_SECONDS)
                    except asyncio.TimeoutError:
                        logger.debug(
                            "Timed out waiting for pid=%d to exit after SIGINT, sending SIGTERM",
                            sub_proc.pid,
                        )
                        proc.terminate()
                        try:
                            await asyncio.wait_for(
                                proc.wait(), timeout=constants.SIGTERM_TIMEOUT_SECONDS)
                        except asyncio.TimeoutError:
                            logger.debug(
                                "Timed out waiting for pid=%d to exit after SIGTERM", sub_proc.pid)
                except BaseException:
                    logger.exception(
                        "Unexpected error when terminating child; pid=%d", sub_proc.pid)
                finally:
                    raise err
            else:
                # In the case that the yielded context block exits without an
                # error we wait for the process to finish naturally.  This can
                # hang indefinitely.
                await proc.wait()
        finally:
            if sub_proc.returncode is None:
                # If the process has not returned at this stage we need to hard
                # kill it to prevent it from hanging.
                logger.warning(
                    "Child process pid=%d failed to exit cleanly.  Sending SIGKILL",
                    sub_proc.pid,
                    # The `any` call is to include a stacktrace if this
                    # happened due to an exception but to omit it if this is
                    # somehow happening outside of an exception context.
                    exc_info=any(sys.exc_info()),
                )
                sub_proc.kill()


async def run_in_process(async_fn: Callable[..., TReturn],
                         *args: Any,
                         loop: asyncio.AbstractEventLoop = None,
                         subprocess_kwargs: 'SubprocessKwargs' = None) -> TReturn:
    proc_ctx = open_in_process(
        async_fn,
        *args,
        loop=loop,
        subprocess_kwargs=subprocess_kwargs,
    )
    async with proc_ctx as proc:
        await proc.wait()
    return proc.get_result_or_raise()
