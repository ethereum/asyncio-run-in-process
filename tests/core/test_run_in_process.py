import asyncio
import os
from pathlib import (
    Path,
)

import pytest


@pytest.mark.asyncio
async def test_run_in_process_touch_file(touch_path, runner):
    async def touch_file(path: Path):
        path.touch()

    assert not touch_path.exists()
    await asyncio.wait_for(runner(touch_file, touch_path), timeout=2)
    assert touch_path.exists()


@pytest.mark.asyncio
async def test_run_in_process_with_result(runner):
    async def return7():
        return 7

    result = await asyncio.wait_for(runner(return7), timeout=2)
    assert result == 7


@pytest.mark.asyncio
async def test_run_in_process_with_error(runner):
    async def raise_err():
        raise ValueError("Some err")

    with pytest.raises(ValueError, match="Some err"):
        await asyncio.wait_for(runner(raise_err), timeout=2)


@pytest.mark.asyncio
async def test_run_in_process_pass_environment_variables(runner):
    # sanity
    assert 'ASYNC_RUN_IN_PROCESS_ENV_TEST' not in os.environ

    async def return_env():
        return os.environ['ASYNC_RUN_IN_PROCESS_ENV_TEST']

    value = await runner(
        return_env,
        subprocess_kwargs={'env': {'ASYNC_RUN_IN_PROCESS_ENV_TEST': 'test-value'}},
    )
    assert value == 'test-value'
