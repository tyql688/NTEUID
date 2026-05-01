from __future__ import annotations

import asyncio
from typing import Any
from collections.abc import Coroutine

from gsuid_core.logger import logger

_BACKGROUND_TASKS: set[asyncio.Task[Any]] = set()


def create_background_task(coro: Coroutine[Any, Any, Any]) -> asyncio.Task[Any]:
    """启动非关键后台任务，并统一记录未捕获异常。"""
    task = asyncio.create_task(coro, name=coro.__qualname__)
    _BACKGROUND_TASKS.add(task)
    task.add_done_callback(_on_done)
    return task


def _on_done(task: asyncio.Task[Any]) -> None:
    _BACKGROUND_TASKS.discard(task)
    if task.cancelled():
        return
    error = task.exception()
    if error is not None:
        logger.warning(f"[NTE后台任务] {task.get_name()} 异常: {error!r}")
