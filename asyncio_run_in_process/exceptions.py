class BaseRunInProcessException(Exception):
    pass


class ProcessKilled(BaseRunInProcessException):
    pass


class InvalidState(BaseRunInProcessException):
    pass


class ChildCancelled(BaseRunInProcessException):
    pass


class UnpickleableValue(BaseRunInProcessException):
    pass


class InvalidDataFromChild(BaseRunInProcessException):
    """
    The child's return value cannot be unpickled.

    This seems to happen only when the child raises a custom exception whose constructor has more
    than one required argument: https://github.com/ethereum/asyncio-run-in-process/issues/28
    """
    pass
