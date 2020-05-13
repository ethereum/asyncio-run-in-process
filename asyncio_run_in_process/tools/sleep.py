from sniffio import (
    current_async_library,
)


async def sleep(duration: float) -> None:
    if current_async_library() == 'trio':
        import trio
        await trio.sleep(duration)
    elif current_async_library() == 'asyncio':
        import asyncio
        await asyncio.sleep(duration)
    else:
        raise Exception("Invariant")
