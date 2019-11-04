asyncio-run-in-process
==============================

Simple asyncio friendly replacement for multiprocessing to run a coroutine in an isolated process

Contents
--------

.. toctree::
    :maxdepth: 3

    asyncio_run_in_process
    releases


Quickstart
----------

We use ``run_in_process`` for something we want run in a process in a blocking manner.

.. code-block:: python

    from asyncio_run_in_process import run_in_process

    async def fib(n):
        if n <= 1:
            return n
        else:
            return await fib(n - 1) + await fib(n - 2)

    # runs in a separate process
    result = await run_in_process(fib, 10)
    print(f"The 10th fibbonacci number is {result}")


We use ``open_in_process`` for something we want to run in the background.

.. code-block:: python

    from asyncio_run_in_process import open_in_process:

    async def fib(n):
        if n <= 1:
            return n
        else:
            return await fib(n - 1) + await fib(n - 2)

    # runs in a separate process
    async with open_in_process(fib, 10) as proc:
        # do some other things here while it runs in the background.
        ...
        # the context will block here until the process has finished.
    # once the context exits the result is available on the process.
    print(f"The 10th fibbonacci number is {proc.result}")


Indices and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
