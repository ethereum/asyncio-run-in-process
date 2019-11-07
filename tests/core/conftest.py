from pathlib import (
    Path,
)
import tempfile

import pytest


@pytest.fixture
def touch_path():
    with tempfile.TemporaryDirectory() as base_dir:
        yield Path(base_dir) / "touch.txt"
