import asyncio
import functools

import rx
import rx.operators as op


def do_async(func, *args, **kwds):
    @functools.wraps(func)
    def wrapper(*fargs, **fkwds):
        return rx.from_future(asyncio.create_task(func(*fargs, **fkwds)))

    return wrapper


def map_async(func, *args, **kwds):
    return op.flat_map(do_async(func, *args, **kwds))
