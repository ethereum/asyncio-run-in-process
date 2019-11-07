import asyncio
import logging
import os
import signal
from typing import (
    Any,
    AsyncContextManager,
    AsyncIterator,
    BinaryIO,
    Callable,
    cast,
)

from async_generator import (
    asynccontextmanager,
)

from ._utils import (
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

logger = logging.getLogger("asyncio-run-in-process")


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
    logger.debug("writing execution data for %s over stdin", proc)
    # pass the child process the serialized `async_fn` and `args`

    with os.fdopen(parent_w, "wb") as to_child:
        to_child.write(proc.sub_proc_payload)
        to_child.flush()

    await proc.wait_for_state(State.WAIT_EXEC_DATA)
    logger.debug("child process %s waiting for exec data", proc)

    await proc.wait_for_state(State.STARTED)
    logger.debug("waiting for process %s finish", proc)

    await sub_proc.wait()

    proc.returncode = sub_proc.returncode
    logger.debug("process %s finished: returncode=%d", proc, proc.returncode)


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
    proc: ProcessAPI[TReturn], from_child: BinaryIO, loop: asyncio.AbstractEventLoop,
) -> None:
    for expected_state in State:
        if proc.state is not expected_state:
            raise InvalidState(
                f"Process in state {proc.state} but expected state {expected_state}"
            )

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


RELAY_SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


def open_in_process(
    async_fn: Callable[..., TReturn],
    *args: Any,
    loop: asyncio.AbstractEventLoop = None,
) -> AsyncContextManager[ProcessAPI[TReturn]]:
    return cast(
        AsyncContextManager[ProcessAPI[TReturn]],
        _open_in_process(async_fn, *args, loop=loop),
    )


# mypy recognizes this decorator as being untyped.
@asynccontextmanager  # type: ignore
async def _open_in_process(
    async_fn: Callable[..., TReturn],
    *args: Any,
    loop: asyncio.AbstractEventLoop = None,
) -> AsyncIterator[ProcessAPI[TReturn]]:
    proc: Process[TReturn] = Process(async_fn, args)

    parent_r, child_w = os.pipe()
    child_r, parent_w = os.pipe()
    parent_pid = os.getpid()

    command = get_subprocess_command(child_r, child_w, parent_pid)

    sub_proc = await asyncio.create_subprocess_exec(
        *command,
        # stdin=subprocess.PIPE,
        # stdout=subprocess.PIPE,
        # stderr=subprocess.PIPE,
        pass_fds=(child_r, child_w),
    )

    if loop is None:
        loop = asyncio.get_event_loop()

    signal_queue: asyncio.Queue[signal.Signals] = asyncio.Queue()

    with os.fdopen(parent_r, "rb", closefd=True) as from_child:

        for signum in RELAY_SIGNALS:
            loop.add_signal_handler(
                signum,
                signal_queue.put_nowait,
                signum,
            )

        # Monitoring
        monitor_sub_proc_task = asyncio.ensure_future(_monitor_sub_proc(proc, sub_proc, parent_w))
        relay_signals_task = asyncio.ensure_future(_relay_signals(proc, signal_queue))
        monitor_state_task = asyncio.ensure_future(_monitor_state(proc, from_child, loop))

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
            yield proc
        except KeyboardInterrupt as err:
            # If a keyboard interrupt is encountered relay it to the
            # child process and then give it a moment to cleanup before
            # re-raising
            try:
                proc.send_signal(signal.SIGINT)
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2)
                except asyncio.TimeoutError:
                    pass
            finally:
                raise err
        finally:
            await proc.wait()

            monitor_sub_proc_task.cancel()
            try:
                await monitor_sub_proc_task
            except asyncio.CancelledError:
                pass

            monitor_state_task.cancel()
            try:
                await monitor_state_task
            except asyncio.CancelledError:
                pass

            relay_signals_task.cancel()
            try:
                await relay_signals_task
            except asyncio.CancelledError:
                pass


async def run_in_process(async_fn: Callable[..., TReturn], *args: Any) -> TReturn:
    async with open_in_process(async_fn, *args) as proc:
        await proc.wait()
    return proc.result
