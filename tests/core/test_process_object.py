import asyncio

import pytest

from asyncio_run_in_process import (
    State,
    open_in_process,
)


@pytest.mark.asyncio
async def test_Process_object_state_api():
    async def return7():
        return 7

    async with open_in_process(return7) as proc:
        assert proc.state.is_on_or_after(State.STARTED)

        await asyncio.wait_for(proc.wait_for_state(State.FINISHED), timeout=2)
        assert proc.state is State.FINISHED
        assert proc.return_value == 7


@pytest.mark.asyncio
async def test_Process_object_wait_for_return_value():
    async def return7():
        return 7

    async with open_in_process(return7) as proc:
        await asyncio.wait_for(proc.wait_return_value(), timeout=2)
        assert proc.return_value == 7


@pytest.mark.asyncio
async def test_Process_object_wait_for_pid():
    async def return7():
        return 7

    async with open_in_process(return7) as proc:
        await asyncio.wait_for(proc.wait_pid(), timeout=2)
        assert isinstance(proc.pid, int)


@pytest.mark.asyncio
async def test_Process_object_wait_for_returncode():
    async def system_exit_123():
        raise SystemExit(123)

    async with open_in_process(system_exit_123) as proc:
        await asyncio.wait_for(proc.wait_returncode(), timeout=2)
        assert proc.returncode == 123


@pytest.mark.asyncio
async def test_Process_object_wait_for_error():
    async def raise_error():
        raise ValueError("child-error")

    async with open_in_process(raise_error) as proc:
        await asyncio.wait_for(proc.wait_error(), timeout=2)
        assert isinstance(proc.error, ValueError)


@pytest.mark.asyncio
async def test_Process_object_wait_for_result_when_error():
    async def raise_error():
        raise ValueError("child-error")

    async with open_in_process(raise_error) as proc:
        with pytest.raises(ValueError, match="child-error"):
            await asyncio.wait_for(proc.wait_result_or_raise(), timeout=2)


@pytest.mark.asyncio
async def test_Process_object_wait_for_result_when_return_value():
    async def return7():
        return 7

    async with open_in_process(return7) as proc:
        result = await asyncio.wait_for(proc.wait_result_or_raise(), timeout=2)
        assert result == 7
        assert proc.error is None


@pytest.mark.asyncio
async def test_Process_object_wait_when_return_value():
    async def return7():
        return 7

    async with open_in_process(return7) as proc:
        await asyncio.wait_for(proc.wait(), timeout=2)
        assert proc.return_value == 7
        assert proc.error is None


@pytest.mark.asyncio
async def test_Process_object_wait_when_error():
    async def raise_error():
        raise ValueError("child-error")

    async with open_in_process(raise_error) as proc:
        await asyncio.wait_for(proc.wait(), timeout=2)
        assert isinstance(proc.error, ValueError)
