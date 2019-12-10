try:
    # mypy knows that `TypedDict` and `Literal` don't exist in <3.8
    from typing import TypedDict, Literal  # type: ignore
except ImportError:
    # TypedDict is only available in python 3.8+
    # Literal is only available in python 3.8+
    from typing_extensions import TypedDict, Literal  # noqa: F401
