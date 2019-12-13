# The number of seconds that are given to a child process to exit after the
# parent process gets a KeyboardInterrupt/SIGINT-signal and sends a `SIGINT` to
# the child process.
SIGINT_TIMEOUT_SECONDS = 2


# The number of seconds that are givent to a child process to exit after the
# parent process gets an `asyncio.CancelledError` which results in sending a
# `SIGTERM` to the child process.
SIGTERM_TIMEOUT_SECONDS = 2
