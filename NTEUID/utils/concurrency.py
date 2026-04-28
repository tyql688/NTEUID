from __future__ import annotations

import asyncio
import inspect
from typing import Any, TypeVar, ParamSpec, overload
from weakref import WeakValueDictionary
from functools import wraps
from collections.abc import Callable, Sequence, Awaitable, MutableMapping

P = ParamSpec("P")
R = TypeVar("R")
B = TypeVar("B")

AsyncFunc = Callable[P, Awaitable[R]]
# 用哨兵值区分“未传 on_busy”和“显式传入 None”。
_MISSING: object = object()


class LockBusyError(TimeoutError):
    pass


@overload
def async_func_lock(
    _func: AsyncFunc[P, R],
    *,
    keys: Sequence[str] | None = None,
    timeout: float | None = None,
    weak: bool = True,
) -> AsyncFunc[P, R]: ...


@overload
def async_func_lock(
    _func: AsyncFunc[P, R],
    *,
    keys: Sequence[str] | None = None,
    timeout: float | None = None,
    weak: bool = True,
    on_busy: B,
) -> Callable[P, Awaitable[R | B]]: ...


@overload
def async_func_lock(
    _func: None = None,
    *,
    keys: Sequence[str] | None = None,
    timeout: float | None = None,
    weak: bool = True,
) -> Callable[[AsyncFunc[P, R]], AsyncFunc[P, R]]: ...


@overload
def async_func_lock(
    _func: None = None,
    *,
    keys: Sequence[str] | None = None,
    timeout: float | None = None,
    weak: bool = True,
    on_busy: B,
) -> Callable[[AsyncFunc[P, R]], Callable[P, Awaitable[R | B]]]: ...


def async_func_lock(
    _func: AsyncFunc[P, R] | None = None,
    *,
    keys: Sequence[str] | None = None,
    timeout: float | None = None,
    weak: bool = True,
    on_busy: object = _MISSING,
) -> Any:
    """给 async 函数按参数值加互斥锁。

    keys 只接受函数签名里的参数名；需要实例级隔离时，把实例标识作为显式参数传入。
    timeout=None 表示排队等待，timeout=0 表示立即放弃，timeout>0 表示限时等待。
    """
    key_names = _normalize_key_names(keys)
    if timeout is not None and timeout < 0:
        raise ValueError("async_func_lock timeout must be >= 0")

    def decorator(func: AsyncFunc[P, R]) -> Callable[P, Awaitable[Any]]:
        sig = inspect.signature(func)
        _validate_key_names(sig, key_names)

        locks: MutableMapping[tuple[str, ...], asyncio.Lock]
        if weak:
            # 高基数 key 默认走弱引用，避免 request_id 这类临时 key 长期留在内存里。
            locks = WeakValueDictionary()
        else:
            locks = {}

        is_method = _is_method_signature(sig)

        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> Any:
            lock_key, busy_msg = _build_lock_key(func, sig, is_method, key_names, args, kwargs)
            lock = locks.get(lock_key)
            if lock is None:
                lock = asyncio.Lock()
                locks[lock_key] = lock

            # fail-fast：只要锁已占用就直接返回 on_busy 或抛 LockBusyError。
            if timeout == 0:
                if lock.locked():
                    if on_busy is _MISSING:
                        raise LockBusyError(busy_msg)
                    return on_busy
                async with lock:
                    return await func(*args, **kwargs)

            # 默认策略：同 key 调用按顺序排队执行。
            if timeout is None:
                async with lock:
                    return await func(*args, **kwargs)

            # 限时等待需要手动 release，避免 wait_for 取消 acquire 后混进 async with 状态。
            try:
                await asyncio.wait_for(lock.acquire(), timeout)
            except TimeoutError as e:
                if on_busy is _MISSING:
                    raise LockBusyError(busy_msg) from e
                return on_busy

            try:
                return await func(*args, **kwargs)
            finally:
                lock.release()

        return wrapper

    return decorator if _func is None else decorator(_func)


def _normalize_key_names(keys: Sequence[str] | None) -> tuple[str, ...]:
    if keys is None:
        return ()
    if isinstance(keys, str):
        raise TypeError("async_func_lock keys must be a sequence of parameter names")

    key_names = tuple(keys)
    # 不支持 self.xxx 这种隐式取值，避免调用侧写错后静默退化成整函数锁。
    invalid = [name for name in key_names if not isinstance(name, str) or "." in name]
    if invalid:
        raise ValueError("async_func_lock keys only accept explicit parameter names")

    duplicates = sorted({name for name in key_names if key_names.count(name) > 1})
    if duplicates:
        raise ValueError(f"async_func_lock duplicate keys: {', '.join(duplicates)}")

    return key_names


def _validate_key_names(sig: inspect.Signature, key_names: tuple[str, ...]) -> None:
    missing = [name for name in key_names if name not in sig.parameters]
    if missing:
        raise ValueError(f"async_func_lock unknown keys: {', '.join(missing)}")


def _is_method_signature(sig: inspect.Signature) -> bool:
    params = tuple(sig.parameters)
    return bool(params) and params[0] in {"self", "cls"}


def _build_lock_key(
    func: Callable[..., Awaitable[Any]],
    sig: inspect.Signature,
    is_method: bool,
    key_names: tuple[str, ...],
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> tuple[tuple[str, ...], str]:
    # bind 会按原函数签名处理默认值、缺参和多余参数，锁 key 与真实调用保持一致。
    bound = sig.bind(*args, **kwargs)
    bound.apply_defaults()

    if is_method:
        # 方法默认按类共享锁；实例级隔离应通过 keys 指向显式参数完成。
        owner = _owner_name(bound.arguments[next(iter(sig.parameters))])
        parts = [func.__module__, owner, func.__name__]
    else:
        parts = [func.__module__, func.__qualname__]

    key_values = [repr(bound.arguments[name]) for name in key_names]
    parts.extend(key_values)

    if key_values:
        busy_msg = f"{func.__name__}({', '.join(key_values)}) busy"
    else:
        busy_msg = f"{func.__name__} busy"

    return tuple(parts), busy_msg


def _owner_name(value: object) -> str:
    if isinstance(value, type):
        return value.__qualname__
    return value.__class__.__qualname__
