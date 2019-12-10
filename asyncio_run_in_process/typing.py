import os
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Callable,
    TypeVar,
)

if TYPE_CHECKING:
    import subprocess
    from typing import Mapping, Optional, Sequence, Union

    from .typing_compat import Literal, TypedDict

    try:
        # mypy knows this isn't present in <=3.6
        from subprocess import STARTUPINFO  # type: ignore
    except ImportError:
        # STARTUPINFO added in 3.7+
        STARTUPINFO = Any

    PIPE = Literal[subprocess.PIPE]
    DEVNULL = Literal[subprocess.DEVNULL]
    STDOUT = Literal[subprocess.STDOUT]

    SubprocessKwargs = TypedDict(
        'SubprocessKwargs',
        # no: bufsize, universal_newlines, shell, text, encoding and errors
        {
            'stdin': Optional[Union[IO, PIPE, DEVNULL]],
            'stdout': Optional[Union[IO, PIPE, DEVNULL]],
            'stderr': Optional[Union[IO, PIPE, DEVNULL, STDOUT]],

            'limit': Optional[int],

            'preexec_fn': Callable[..., Any],
            'close_fds': Optional[bool],
            'pass_fds': Optional[Sequence[int]],
            'cdw': Optional[os.PathLike],
            'restore_signals': Optional[bool],
            'start_new_session': Optional[bool],
            'env': Optional[Mapping[str, str]],
            'startupinfo': Optional[STARTUPINFO],
            'creationflags': Optional[Union[
                Union[
                    Literal[subprocess.CREATE_NEW_CONSOLE],  # type: ignore
                    Literal[subprocess.CREATE_NEW_PROCESS_GROUP],  # type: ignore
                    Literal[subprocess.ABOVE_NORMAL_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.BELOW_NORMAL_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.HIGH_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.IDLE_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.NORMAL_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.REALTIME_PRIORITY_CLASS],  # type: ignore
                    Literal[subprocess.CREATE_NO_WINDOW],  # type: ignore
                    Literal[subprocess.DETACHED_PROCESS],  # type: ignore
                    Literal[subprocess.CREATE_DEFAULT_ERROR_MODE],  # type: ignore
                    Literal[subprocess.CREATE_BREAKAWAY_FROM_JOB],  # type: ignore
                ],
                Sequence[Union[
                    Literal[subprocess.CREATE_NEW_CONSOLE],
                    Literal[subprocess.CREATE_NEW_PROCESS_GROUP],
                    Literal[subprocess.ABOVE_NORMAL_PRIORITY_CLASS],
                    Literal[subprocess.BELOW_NORMAL_PRIORITY_CLASS],
                    Literal[subprocess.HIGH_PRIORITY_CLASS],
                    Literal[subprocess.IDLE_PRIORITY_CLASS],
                    Literal[subprocess.NORMAL_PRIORITY_CLASS],
                    Literal[subprocess.REALTIME_PRIORITY_CLASS],
                    Literal[subprocess.CREATE_NO_WINDOW],
                    Literal[subprocess.DETACHED_PROCESS],
                    Literal[subprocess.CREATE_DEFAULT_ERROR_MODE],
                    Literal[subprocess.CREATE_BREAKAWAY_FROM_JOB],
                ]],
            ]],
        },
        total=False,
    )


TReturn = TypeVar("TReturn")
