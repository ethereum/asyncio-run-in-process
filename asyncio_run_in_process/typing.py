import os
from typing import (
    IO,
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    TypeVar,
)

if TYPE_CHECKING:
    #
    # This block ensures that typing_extensions isn't needed during runtime and
    # is only necessary for linting.
    #
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
                Literal[
                    subprocess.CREATE_NEW_CONSOLE,  # type: ignore
                    subprocess.CREATE_NEW_PROCESS_GROUP,  # type: ignore
                    subprocess.ABOVE_NORMAL_PRIORITY_CLASS,  # type: ignore
                    subprocess.BELOW_NORMAL_PRIORITY_CLASS,  # type: ignore
                    subprocess.HIGH_PRIORITY_CLASS,  # type: ignore
                    subprocess.IDLE_PRIORITY_CLASS,  # type: ignore
                    subprocess.NORMAL_PRIORITY_CLASS,  # type: ignore
                    subprocess.REALTIME_PRIORITY_CLASS,  # type: ignore
                    subprocess.CREATE_NO_WINDOW,  # type: ignore
                    subprocess.DETACHED_PROCESS,  # type: ignore
                    subprocess.CREATE_DEFAULT_ERROR_MODE,  # type: ignore
                    subprocess.CREATE_BREAKAWAY_FROM_JOB,  # type: ignore
                ],
                Sequence[Literal[
                    subprocess.CREATE_NEW_CONSOLE,
                    subprocess.CREATE_NEW_PROCESS_GROUP,
                    subprocess.ABOVE_NORMAL_PRIORITY_CLASS,
                    subprocess.BELOW_NORMAL_PRIORITY_CLASS,
                    subprocess.HIGH_PRIORITY_CLASS,
                    subprocess.IDLE_PRIORITY_CLASS,
                    subprocess.NORMAL_PRIORITY_CLASS,
                    subprocess.REALTIME_PRIORITY_CLASS,
                    subprocess.CREATE_NO_WINDOW,
                    subprocess.DETACHED_PROCESS,
                    subprocess.CREATE_DEFAULT_ERROR_MODE,
                    subprocess.CREATE_BREAKAWAY_FROM_JOB,
                ]],
            ]],
        },
        total=False,
    )
else:
    # Ensure this is importable outside of the `TYPE_CHECKING` context so that
    # 3rd party libraries can use this as a type without having to think too
    # much about what they are doing.
    SubprocessKwargs = Dict[str, Any]


TReturn = TypeVar("TReturn")
