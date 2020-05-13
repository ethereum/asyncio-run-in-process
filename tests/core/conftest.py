from pathlib import (
    Path,
)
import tempfile

import pytest

from asyncio_run_in_process import (
    run_in_process,
    run_in_process_with_trio,
)


@pytest.fixture
def touch_path():
    with tempfile.TemporaryDirectory() as base_dir:
        yield Path(base_dir) / "touch.txt"


@pytest.fixture(params=('use_trio', 'use_asyncio'))
def runner(request):
    if request.param == 'use_trio':
        return run_in_process_with_trio
    elif request.param == 'use_asyncio':
        return run_in_process
    else:
        raise Exception("Invariant")
