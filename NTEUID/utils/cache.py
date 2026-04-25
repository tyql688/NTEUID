import time
import asyncio
from typing import Any
from functools import wraps
from collections import OrderedDict
from collections.abc import Callable


def _now() -> float:
    # 单调时钟不受系统时间校准影响，适合做 TTL 判断。
    return time.monotonic()


class TimedCache:
    def __init__(self, timeout: float = 300.0, maxsize: int = 32) -> None:
        if timeout < 0:
            raise ValueError("TimedCache timeout must be >= 0")
        if maxsize <= 0:
            raise ValueError("TimedCache maxsize must be > 0")

        self._store: OrderedDict[str, tuple[Any, float]] = OrderedDict()
        self._timeout = timeout
        self._maxsize = maxsize

    def set(self, key: str, value: Any) -> None:
        self._sweep()

        if key in self._store:
            # 更新已有 key 不会增加容量，不应该触发 LRU 淘汰。
            self._store.move_to_end(key)
        else:
            while len(self._store) >= self._maxsize:
                self._store.popitem(last=False)

        self._store[key] = (value, _now() + self._timeout)

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None

        value, expire_at = entry
        if expire_at <= _now():
            self._store.pop(key, None)
            return None

        self._store.move_to_end(key)
        return value

    def pop(self, key: str) -> Any | None:
        entry = self._store.pop(key, None)
        if entry is None:
            return None

        value, expire_at = entry
        if expire_at <= _now():
            return None
        return value

    def _sweep(self) -> None:
        now = _now()
        expired_keys = [key for key, (_, expire_at) in self._store.items() if expire_at <= now]
        for key in expired_keys:
            self._store.pop(key, None)


def timed_async_cache(expiration: float, condition: Callable[[Any], bool] = bool):
    """异步函数 TTL 缓存。key 绑定到 `ClassName.method_name`（或函数名），不区分入参；
    若哪天需要按入参分桶，直接把 key 算法改成带参数指纹即可。"""
    if expiration < 0:
        raise ValueError("timed_async_cache expiration must be >= 0")

    def decorator(func):
        cache: dict[str, tuple[Any, float]] = {}
        locks: dict[str, asyncio.Lock] = {}

        @wraps(func)
        async def wrapper(*args, **kwargs):
            cache_key = f"{args[0].__class__.__name__}.{func.__name__}" if args else func.__name__
            now = _now()

            hit = cache.get(cache_key)
            if hit is not None and now - hit[1] < expiration:
                return hit[0]

            lock = locks.setdefault(cache_key, asyncio.Lock())
            async with lock:
                # 进入锁后重新取时间，避免排队期间用旧时间判断缓存有效期。
                now = _now()
                hit = cache.get(cache_key)
                if hit is not None and now - hit[1] < expiration:
                    return hit[0]

                value = await func(*args, **kwargs)
                if condition(value):
                    cache[cache_key] = (value, now)
                return value

        return wrapper

    return decorator
