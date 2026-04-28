from __future__ import annotations

import random
import asyncio

from gsuid_core.logger import logger

from ..utils.msgs import SignMsg
from .sign_service import sign_account
from ..utils.database import NTEUser
from ..nte_config.nte_config import NTEConfig

# 同一账号 (center_uid) 串行：批量/手动撞上时后到者 fail-fast，避免 refresh_token 竞态
_account_locks: dict[str, asyncio.Lock] = {}

# 批量任务全局互斥：手动"全部签到" + 定时 cron 撞上时只有一个真跑，另一个跳过
batch_lock = asyncio.Lock()


async def run_user_sign(user_id: str, bot_id: str) -> str:
    users = await NTEUser.list_sign_targets_by_user(user_id, bot_id)
    if not users:
        return SignMsg.not_logged_in()
    blocks = [await _sign_locked(g) for g in _group_by_center(users)]
    return "\n".join(blocks) if len(blocks) == 1 else "\n---\n".join(blocks)


async def run_all_sign() -> str | None:
    """繁忙返回 None，调用方决定用 send_nte_notify 发忙提示。"""
    if batch_lock.locked():
        return None
    async with batch_lock:
        return await _run_batch(await NTEUser.list_sign_targets_all(), "异环全部签到：")


async def run_scheduled_sign() -> str | None:
    if batch_lock.locked():
        return None
    async with batch_lock:
        if NTEConfig.get_config("NTESignAll").data:
            users, header = await NTEUser.list_sign_targets_all(), "异环定时签到（全员）："
        else:
            users, header = await NTEUser.list_sign_subscribers(), "异环定时签到（订阅）："
        return await _run_batch(users, header)


async def _run_batch(users: list[NTEUser], header: str) -> str:
    if not users:
        return f"{header}\n  · {SignMsg.NO_SIGN_ACCOUNT}"
    groups = _group_by_center(users)
    semaphore = asyncio.Semaphore(NTEConfig.get_config("NTESignConcurrency").data)
    delay_lo, delay_hi = NTEConfig.get_config("NTESignBatchDelay").data

    async def _runner(group: list[NTEUser]) -> str:
        async with semaphore:
            await asyncio.sleep(random.uniform(delay_lo, delay_hi))
            return await _sign_locked(group)

    # return_exceptions=True：单账号异常不带走整批，最多漏它一个
    results = await asyncio.gather(
        *(_runner(g) for g in groups),
        return_exceptions=True,
    )
    blocks: list[str] = []
    for group, result in zip(groups, results):
        center_uid = group[0].center_uid
        if isinstance(result, str):
            blocks.append(result)
        else:
            logger.warning(f"[NTE签到] 账号 {center_uid} 签到异常: {result!r}")
            blocks.append(f"[账号 {center_uid}]\n  · {SignMsg.FAILED}")
    return "\n".join([header, *blocks])


async def _sign_locked(users: list[NTEUser]) -> str:
    """账号级互斥壳：lock.locked() 快判，已在签就跳过，不排队。"""
    center_uid = users[0].center_uid
    lock = _account_locks.get(center_uid)
    if lock is None:
        lock = _account_locks[center_uid] = asyncio.Lock()
    if lock.locked():
        return f"[账号 {center_uid}] {SignMsg.ACCOUNT_BUSY}"
    async with lock:
        return await sign_account(users)


def _group_by_center(users: list[NTEUser]) -> list[list[NTEUser]]:
    groups: dict[str, list[NTEUser]] = {}
    for user in users:
        groups.setdefault(user.center_uid, []).append(user)
    return list(groups.values())
