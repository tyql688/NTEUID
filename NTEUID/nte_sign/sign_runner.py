from __future__ import annotations

import random
import asyncio
from weakref import WeakValueDictionary
from dataclasses import dataclass

from gsuid_core.logger import logger

from ..utils.msgs import SignMsg
from .sign_service import (
    STATUS_OK,
    STATUS_FAIL,
    STATUS_SKIP,
    TASK_LABELS,
    AccountStatus,
    SignAccountResult,
    sign_account,
)
from ..utils.database import NTEUser
from ..utils.game_registry import GAME_LABELS
from ..nte_config.nte_config import NTEConfig

# 同一账号 (center_uid) 串行：批量/手动撞上时后到者 fail-fast，避免 refresh_token 竞态。
# weak：cm 持有期间 lock 不会被回收；用完释放后 dict entry 自动失效，避免历史 center_uid 永久占位。
_account_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()

# 批量任务全局互斥：手动"全部签到" + 定时 cron 撞上时只有一个真跑，另一个跳过
batch_lock = asyncio.Lock()


@dataclass(frozen=True)
class PerUserSignReport:
    """`(user_id, bot_id)` 维度的签到汇总，给推送层按订阅清单分发。"""

    user_id: str
    bot_id: str
    text: str
    has_failure: bool


@dataclass
class _StatusCounter:
    ok: int = 0
    skip: int = 0
    fail: int = 0

    def add(self, status: str) -> None:
        if status == STATUS_OK:
            self.ok += 1
        elif status == STATUS_SKIP:
            self.skip += 1
        elif status == STATUS_FAIL:
            self.fail += 1

    @property
    def total(self) -> int:
        return self.ok + self.skip + self.fail

    def render(self) -> str:
        return f"{STATUS_OK} {self.ok}  {STATUS_SKIP} {self.skip}  {STATUS_FAIL} {self.fail}"


async def run_user_sign(user_id: str, bot_id: str) -> str:
    users = await NTEUser.list_sign_targets_by_user(user_id, bot_id)
    if not users:
        return SignMsg.not_logged_in()
    blocks = [(await _sign_locked(g)).text for g in _group_by_center(users)]
    return "\n".join(blocks) if len(blocks) == 1 else "\n---\n".join(blocks)


async def run_all_sign() -> tuple[str, list[PerUserSignReport]] | None:
    """繁忙返回 None；输出与 `run_scheduled_sign` 对齐。"""
    if batch_lock.locked():
        return None
    async with batch_lock:
        return await _run_batch(await NTEUser.list_sign_targets_all(), "异环全部签到：")


async def run_scheduled_sign() -> tuple[str, list[PerUserSignReport]] | None:
    """繁忙返回 None；返回 `(全局汇总, per-user 子报告)`。"""
    if batch_lock.locked():
        return None
    async with batch_lock:
        if NTEConfig.get_config("NTESignAll").data:
            users, header = await NTEUser.list_sign_targets_all(), "异环定时签到（全员）："
        else:
            users, header = await NTEUser.list_sign_subscribers(), "异环定时签到（订阅）："
        return await _run_batch(users, header)


async def _run_batch(users: list[NTEUser], header: str) -> tuple[str, list[PerUserSignReport]]:
    if not users:
        return f"{header}\n  · {SignMsg.NO_SIGN_ACCOUNT}", []
    groups = _group_by_center(users)
    semaphore = asyncio.Semaphore(NTEConfig.get_config("NTESignConcurrency").data)
    delay_lo, delay_hi = NTEConfig.get_config("NTESignBatchDelay").data

    async def _runner(group: list[NTEUser]) -> SignAccountResult:
        async with semaphore:
            await asyncio.sleep(random.uniform(delay_lo, delay_hi))
            return await _sign_locked(group)

    # return_exceptions=True：单账号异常不带走整批，最多漏它一个
    raw = await asyncio.gather(
        *(_runner(g) for g in groups),
        return_exceptions=True,
    )
    results: list[SignAccountResult] = []
    crashed = 0
    for group, item in zip(groups, raw):
        if isinstance(item, BaseException):
            logger.warning(f"[NTE签到] 账号 {group[0].center_uid} 签到异常: {item!r}")
            crashed += 1
        else:
            results.append(item)
    summary = _format_batch_summary(header, results, crashed)
    reports = _aggregate_per_user(groups, raw)
    return summary, reports


def _aggregate_per_user(
    groups: list[list[NTEUser]],
    raw: list[SignAccountResult | BaseException],
) -> list[PerUserSignReport]:
    """同 `(user_id, bot_id)` 下多 center_uid 文本拼起来；任一失败标 has_failure。
    全部 center_uid 都是 ALL_DONE（本地短路无动作）的 user 直接跳过，不进推送。"""
    texts: dict[tuple[str, str], list[str]] = {}
    failed: dict[tuple[str, str], bool] = {}
    has_action: dict[tuple[str, str], bool] = {}
    for group, item in zip(groups, raw):
        primary = group[0]
        key = (primary.user_id, primary.bot_id)
        if isinstance(item, BaseException):
            texts.setdefault(key, []).append(f"[塔吉多账号 {primary.center_uid}] · 签到异常")
            failed[key] = True
            has_action[key] = True
            continue
        texts.setdefault(key, []).append(item.text)
        failed[key] = failed.get(key, False) or item.status in {
            AccountStatus.PARTIAL_FAILED,
            AccountStatus.AUTH_FAILED,
            AccountStatus.BUSY,
        }
        if item.status != AccountStatus.ALL_DONE:
            has_action[key] = True
    return [
        PerUserSignReport(
            user_id=user_id,
            bot_id=bot_id,
            text="\n---\n".join(texts[(user_id, bot_id)]),
            has_failure=failed[(user_id, bot_id)],
        )
        for (user_id, bot_id) in texts
        if has_action.get((user_id, bot_id))
    ]


_DONE_GROUPS: list[tuple[AccountStatus, str]] = [
    (AccountStatus.SUCCESS, "✅ 成功"),
    (AccountStatus.PARTIAL_FAILED, "⚠️ 部分失败"),
    (AccountStatus.ALL_DONE, "⏭️ 已签"),
]
_UNDONE_GROUPS: list[tuple[AccountStatus, str]] = [
    (AccountStatus.AUTH_FAILED, "❌ 登录失效"),
    (AccountStatus.BUSY, "🔒 占用中"),
]


def _format_batch_summary(header: str, results: list[SignAccountResult], crashed: int) -> str:
    buckets: dict[AccountStatus, int] = {s: 0 for s in AccountStatus}
    for r in results:
        buckets[r.status] += 1
    total_accounts = len(results) + crashed

    done_total = sum(buckets[s] for s, _ in _DONE_GROUPS)
    undone_total = sum(buckets[s] for s, _ in _UNDONE_GROUPS) + crashed

    lines: list[str] = [header, f"塔吉多账号：{total_accounts} 个"]
    if done_total:
        parts = [f"{label} {buckets[s]}" for s, label in _DONE_GROUPS if buckets[s]]
        lines.append(f"完成 {done_total}：{' / '.join(parts)}")
    if undone_total:
        parts = [f"{label} {buckets[s]}" for s, label in _UNDONE_GROUPS if buckets[s]]
        if crashed:
            parts.append(f"💥 异常 {crashed}")
        lines.append(f"未签 {undone_total}：{' / '.join(parts)}")

    app = _StatusCounter()
    for r in results:
        if r.app is not None:
            app.add(r.app.status)
    if app.total:
        lines.append(f"塔吉多 App 签到：{app.render()}")

    games: dict[str, _StatusCounter] = {}
    for r in results:
        for game_id, steps in r.games.items():
            counter = games.setdefault(game_id, _StatusCounter())
            for step in steps:
                counter.add(step.status)
    for game_id, counter in games.items():
        label = GAME_LABELS.get(game_id, game_id)
        lines.append(f"{label} 游戏签到：{counter.render()}（{counter.total} 角色）")

    tasks: dict[str, _StatusCounter] = {}
    tasks_global_failed = 0
    for r in results:
        if r.tasks_global_failed:
            tasks_global_failed += 1
        for task_key, step in r.tasks.items():
            counter = tasks.setdefault(task_key, _StatusCounter())
            counter.add(step.status)
    for task_key, label in TASK_LABELS.items():
        counter = tasks.get(task_key)
        if counter is not None and counter.total:
            lines.append(f"社区·{label}：{counter.render()}")
    if tasks_global_failed:
        lines.append(f"社区任务整体抓取失败：{tasks_global_failed} 账号")

    return "\n".join(lines)


async def _sign_locked(users: list[NTEUser]) -> SignAccountResult:
    """账号级互斥壳：lock.locked() 快判，已在签就跳过、不排队，避免 refresh_token 竞态。

    `batch_lock` 只保证两个批量不重叠，不管手动；因此两条路径都可能撞 BUSY：
      - 手动 run_user_sign 撞上正在跑的批量
      - 批量 _runner 撞上正在跑的手动签到
    BUSY 是 AccountStatus 的一档，批量统计里有 `占用中` 桶单独计入，不混进成功 / 已签。
    """
    center_uid = users[0].center_uid
    lock = _account_locks.get(center_uid)
    if lock is None:
        lock = _account_locks[center_uid] = asyncio.Lock()
    if lock.locked():
        return SignAccountResult(
            center_uid=center_uid,
            text=f"[塔吉多账号 {center_uid}] · {SignMsg.ACCOUNT_BUSY}",
            status=AccountStatus.BUSY,
        )
    async with lock:
        return await sign_account(users)


def _group_by_center(users: list[NTEUser]) -> list[list[NTEUser]]:
    groups: dict[str, list[NTEUser]] = {}
    for user in users:
        groups.setdefault(user.center_uid, []).append(user)
    return list(groups.values())
