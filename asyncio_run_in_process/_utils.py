import io
import sys
from typing import (
    Any,
    BinaryIO,
    Tuple,
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
