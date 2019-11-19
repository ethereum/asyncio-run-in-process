import logging
import os
import sys

import cloudpickle

from asyncio_run_in_process._utils import (
    RemoteException,
)


def test_RemoteException(caplog):
    logger = logging.getLogger('asyncio_run_in_process.testing')

    def recorder_func():
        try:
            outer_func()
        except Exception:
            _, exc_value, exc_tb = sys.exc_info()
            remote_err = RemoteException(exc_value, exc_tb)

        local_err = cloudpickle.loads(cloudpickle.dumps(remote_err))

        try:
            raise local_err
        except BaseException:
            logger.debug("Got Error:", exc_info=True)

        return local_err

    def outer_func():
        inner_func()

    def inner_func():
        raise ValueError("Some Error")

    with caplog.at_level(logging.DEBUG):
        local_err = recorder_func()
    assert isinstance(local_err, ValueError)
    assert "Some Error" in caplog.text
    assert "outer_func" in caplog.text
    assert "inner_func" in caplog.text
    assert str(os.getpid()) in caplog.text
