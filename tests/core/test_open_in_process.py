import asyncio
import pickle
import signal

import pytest

from asyncio_run_in_process import (
    ProcessKilled,
    open_in_process,
)


@pytest.mark.asyncio
async def test_open_in_proc_SIGTERM_while_running():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    async with open_in_process(do_sleep_forever) as proc:
        proc.terminate()
    assert proc.returncode == 15


@pytest.mark.asyncio
async def test_open_in_proc_SIGKILL_while_running():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    async with open_in_process(do_sleep_forever) as proc:
        await proc.kill()
    assert proc.returncode == -9
    assert isinstance(proc.error, ProcessKilled)


@pytest.mark.asyncio
async def test_open_proc_SIGINT_while_running():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    async with open_in_process(do_sleep_forever) as proc:
        proc.send_signal(signal.SIGINT)
    assert proc.returncode == 2


@pytest.mark.asyncio
async def test_open_proc_SIGINT_can_be_handled():
    async def do_sleep_forever():
        try:
            while True:
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            return 9999

    async with open_in_process(do_sleep_forever) as proc:
        proc.send_signal(signal.SIGINT)
    assert proc.returncode == 0
    assert proc.result == 9999


@pytest.mark.asyncio
async def test_open_proc_SIGINT_can_be_ignored():
    async def do_sleep_forever():
        try:
            while True:
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            # silence the first SIGINT
            pass

        try:
            while True:
                await asyncio.sleep(0)
        except KeyboardInterrupt:
            return 9999

    async with open_in_process(do_sleep_forever) as proc:
        proc.send_signal(signal.SIGINT)
        await asyncio.sleep(0.01)
        proc.send_signal(signal.SIGINT)

    assert proc.returncode == 0
    assert proc.result == 9999


@pytest.mark.asyncio
async def test_open_proc_KeyboardInterrupt_while_running():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    with pytest.raises(KeyboardInterrupt):
        async with open_in_process(do_sleep_forever) as proc:
            raise KeyboardInterrupt
    assert proc.returncode == 2


@pytest.mark.asyncio
async def test_open_proc_invalid_function_call():
    async def takes_no_args():
        pass

    async with open_in_process(takes_no_args, 1, 2, 3) as proc:
        pass
    assert proc.returncode == 1
    assert isinstance(proc.error, TypeError)


@pytest.mark.asyncio
async def test_open_proc_unpickleable_params(touch_path):
    async def takes_open_file(f):
        pass

    with pytest.raises(pickle.PickleError):
        with open(touch_path, "w") as touch_file:
            async with open_in_process(takes_open_file, touch_file):
                # this code block shouldn't get executed
                assert False


@pytest.mark.asyncio
async def test_open_proc_outer_KeyboardInterrupt():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    with pytest.raises(KeyboardInterrupt):
        async with open_in_process(do_sleep_forever) as proc:
            raise KeyboardInterrupt
    assert proc.returncode == 2


class CustomException(BaseException):
    pass


@pytest.mark.asyncio
async def test_open_proc_does_not_hang_on_exception():
    async def do_sleep_forever():
        while True:
            await asyncio.sleep(0)

    async def _do_inner():
        with pytest.raises(CustomException):
            async with open_in_process(do_sleep_forever):
                raise CustomException("Just a boring exception")

    await asyncio.wait_for(_do_inner(), timeout=1)
