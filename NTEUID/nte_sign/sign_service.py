from __future__ import annotations

import random
import asyncio
from typing import Dict, List, Tuple, Optional

from gsuid_core.logger import logger

from ..utils.msgs import SignMsg
from ..utils.session import ensure_tajiduo_client
from ..utils.database import (
    SIGN_KIND_APP,
    SIGN_KIND_GAME,
    SIGN_KIND_TASK_PREFIX,
    NTEUser,
    NTESignRecord,
)
from ..utils.constants import (
    TASK_KEY_SHARE,
    TASK_KEY_LIKE_POST,
    TASK_KEY_BROWSE_POST,
    YIHUAN_TASK_COMMUNITY_IDS,
    TAJIDUO_SIGNIN_COMMUNITY_ID,
)
from ..utils.sdk.tajiduo import TajiduoClient
from ..utils.game_registry import GAME_SIGN_SWITCHES
from ..nte_config.nte_config import NTEConfig
from ..utils.sdk.tajiduo_model import (
    UserTask,
    TajiduoError,
    CommunitySignResult,
)

STATUS_OK = "✅"
STATUS_SKIP = "🚫"
STATUS_FAIL = "❌"

_TASK_LABELS = {
    TASK_KEY_BROWSE_POST: "浏览帖子",
    TASK_KEY_LIKE_POST: "点赞帖子",
    TASK_KEY_SHARE: "分享帖子",
}


async def sign_account(users: List[NTEUser]) -> str:
    """单账号完整签到：refresh → App 签 → 角色游戏签 → 社区任务。
    假设调用方已持有该 center_uid 的账号级锁，内部不再加锁。
    进程级锁：`sign_runner._account_locks` 仅挡单进程竞态；多实例/多进程部署下
    两层幂等会退化为"仅远程 state + POST 去重"，需注意。
    """
    primary = users[0]
    header = f"[账号 {primary.center_uid}]"

    try:
        client = await ensure_tajiduo_client(primary)
    except TajiduoError as error:
        await NTEUser.mark_invalid_by_cookie(primary.cookie, "refresh 失败")
        logger.warning(f"[NTE签到] 账号 {primary.center_uid} 刷新失败: {error.message}")
        return f"{header}\n  · {SignMsg.LOGIN_EXPIRED}"

    lines: List[str] = [header, f"  · {await _app_sign(client, primary.center_uid)}"]
    disabled_games = {
        gid
        for gid, switch in GAME_SIGN_SWITCHES.items()
        if switch is not None and not NTEConfig.get_config(switch).data
    }
    roles = [u for u in users if u.game_id not in disabled_games]

    if roles:
        for user in roles:
            lines.append(f"  · {await _game_sign(client, user)}")
    else:
        lines.append(f"  · {SignMsg.NO_ROLE}")

    if NTEConfig.get_config("NTETaskDaily").data:
        lines.extend(f"  · {line}" for line in await _daily_tasks(client, primary.center_uid))
    return "\n".join(lines)


async def _app_sign(client: TajiduoClient, center_uid: str) -> str:
    label = "塔吉多签到"
    if await NTESignRecord.is_signed(center_uid, SIGN_KIND_APP):
        return _fmt(label, STATUS_SKIP, "今日已签")

    try:
        if await client.get_community_sign_state(TAJIDUO_SIGNIN_COMMUNITY_ID):
            await NTESignRecord.record(
                center_uid, SIGN_KIND_APP, payload={"path": "state_hit", "community_id": TAJIDUO_SIGNIN_COMMUNITY_ID}
            )
            return _fmt(label, STATUS_SKIP, "今日已签")
        result = await client.app_signin(TAJIDUO_SIGNIN_COMMUNITY_ID)
    except TajiduoError as error:
        if _is_already_signed(error):
            await NTESignRecord.record(center_uid, SIGN_KIND_APP, payload=error.raw)
            return _fmt(label, STATUS_SKIP, "今日已签")
        logger.warning(f"[NTE签到] 账号 {center_uid} 塔吉多签到失败: {error.message}")
        return _fmt(label, STATUS_FAIL, SignMsg.FAILED)

    await NTESignRecord.record(center_uid, SIGN_KIND_APP, payload=result.model_dump(by_alias=True))
    return _fmt(label, STATUS_OK, _format_app_rewards(result))


async def _game_sign(client: TajiduoClient, user: NTEUser) -> str:
    """`/apihub/awapi/signin/state` 是账号级（不带 role_id），今日状态不能用来
    跳过单个角色的签到——只走本地 record 幂等 + POST 响应判定。
    """
    label = f"{user.role_name} 游戏签到"
    record_ref = f"{user.game_id}:{user.uid}"
    if await NTESignRecord.is_signed(record_ref, SIGN_KIND_GAME):
        return _fmt(label, STATUS_SKIP, "今日已签")

    try:
        data = await client.game_signin(user.uid, user.game_id)
    except TajiduoError as error:
        if _is_already_signed(error):
            await NTESignRecord.record(record_ref, SIGN_KIND_GAME, payload=error.raw)
            return _fmt(label, STATUS_SKIP, "今日已签")
        logger.warning(f"[NTE签到] 角色 {user.uid} 游戏签到失败: {error.message}")
        return _fmt(label, STATUS_FAIL, SignMsg.FAILED)

    await NTESignRecord.record(record_ref, SIGN_KIND_GAME, payload=data)
    return _fmt(label, STATUS_OK)


async def _daily_tasks(client: TajiduoClient, center_uid: str) -> List[str]:
    try:
        return await _run_daily_tasks(client, center_uid)
    except TajiduoError as error:
        logger.warning(f"[NTE签到] 账号 {center_uid} 社区任务失败: {error.message}")
        return [_fmt("社区任务", STATUS_FAIL, "稍后再试")]


async def _run_daily_tasks(client: TajiduoClient, center_uid: str) -> List[str]:
    """先按本地 NTESignRecord 幂等短路；只有存在未完成子任务时才拉远程 task 列表。
    `like_post` 返回 True 只代表动作成功，不必然等于服务端任务计数 +1；本地落库
    后同日不再重新跑，避免"远程计数滞后→UI 显示 ✅ 但其实没入账"的错觉。
    """
    enabled = set(NTEConfig.get_config("NTETaskKinds").data)
    enabled_keys = [key for key in _TASK_LABELS if key in enabled]
    if not enabled_keys:
        return []

    local_done: Dict[str, bool] = {}
    for key in enabled_keys:
        local_done[key] = await NTESignRecord.is_signed(center_uid, SIGN_KIND_TASK_PREFIX + key)

    pending_keys = [key for key in enabled_keys if not local_done[key]]
    tasks_by_key: Dict[str, UserTask] = {}
    if pending_keys:
        tasks = await client.get_user_tasks()
        tasks_by_key = {t.task_key: t for t in tasks.daily if t.task_key in pending_keys}

    max_failures = int(NTEConfig.get_config("NTETaskMaxFailures").data)
    delay_window = _delay_window("NTETaskActionDelay")
    needed = sum(t.remaining for t in tasks_by_key.values() if not t.finished)

    post_ids: Optional[List[str]] = None
    lines: List[str] = []
    for key in enabled_keys:
        label = _TASK_LABELS[key]
        if local_done[key]:
            lines.append(_fmt(label, STATUS_SKIP, "今日已完成"))
            continue

        task = tasks_by_key.get(key)
        if task is None:
            lines.append(_fmt(label, STATUS_FAIL, "任务未开放"))
            continue

        if task.finished:
            await NTESignRecord.record(
                center_uid,
                SIGN_KIND_TASK_PREFIX + key,
                payload={
                    "path": "server_finished",
                    "complete_times": task.complete_times,
                    "limit_times": task.limit_times,
                },
            )
            lines.append(_fmt(label, STATUS_SKIP, f"今日已完成 {task.complete_times}/{task.limit_times}"))
            continue

        if post_ids is None:
            post_ids = await _collect_post_ids(client, needed=needed)
        if not post_ids:
            lines.append(_fmt(label, STATUS_FAIL, "暂无可处理帖子"))
            continue

        # 每个任务一份独立乱序的帖子列表，避免同一 post 在短时间被 view/like/share 依次命中
        shuffled = random.sample(post_ids, len(post_ids))
        done, failed = await _advance_task(client, task, shuffled, max_failures, delay_window)
        reached = task.complete_times + done
        status = STATUS_OK if reached >= task.limit_times else STATUS_FAIL
        detail = f"{reached}/{task.limit_times}" + (f" 失败 {failed}" if failed else "")

        if status == STATUS_OK:
            await NTESignRecord.record(
                center_uid,
                SIGN_KIND_TASK_PREFIX + key,
                payload={
                    "path": "local_completed",
                    "complete_times_before": task.complete_times,
                    "done": done,
                    "failed": failed,
                    "limit_times": task.limit_times,
                },
            )

        lines.append(_fmt(label, status, detail))
    return lines


async def _advance_task(
    client: TajiduoClient,
    task: UserTask,
    post_ids: List[str],
    max_failures: int,
    delay: Tuple[float, float],
) -> Tuple[int, int]:
    """返回 (成功推进次数, 累计失败数)。连续失败 ≥ max_failures 即熔断。
    `like_post` 返回 False 表示该帖已点过、本次不计入——视作"此帖不可推进"，
    跳到下一帖，不计 done 也不累加失败。
    """
    done = 0
    consecutive_fail = 0
    total_fail = 0
    for post_id in post_ids:
        if done >= task.remaining:
            break
        counted = False
        try:
            if task.task_key == TASK_KEY_BROWSE_POST:
                await client.view_post(post_id)
                counted = True
            elif task.task_key == TASK_KEY_LIKE_POST:
                counted = await client.like_post(post_id)
            elif task.task_key == TASK_KEY_SHARE:
                await client.share_post(post_id)
                counted = True
            else:
                raise AssertionError(f"派发缺失 task_key={task.task_key}")
        except TajiduoError as error:
            consecutive_fail += 1
            total_fail += 1
            if consecutive_fail >= max_failures:
                logger.warning(f"[NTE签到] 任务 {task.task_key} 连续失败 {consecutive_fail} 次熔断: {error.message}")
                break
        else:
            if counted:
                done += 1
                consecutive_fail = 0
        await asyncio.sleep(random.uniform(*delay))
    return done, total_fail


async def _collect_post_ids(client: TajiduoClient, needed: int = 20) -> List[str]:
    """拉帖子列表，若首页可用帖子不足则翻到 page=2。已浏览 / 已点赞过的帖子
    后端仍会返回、但对应任务会返回 False 或 200 无效果，所以这里只做去重 + 翻页，
    具体可用性交给 `_advance_task` 处理。
    """
    ids: List[str] = []
    seen: set[str] = set()
    for community_id in YIHUAN_TASK_COMMUNITY_IDS:
        for page in (1, 2):
            result = await client.list_recommend_posts(community_id, page=page)
            for post in result.posts:
                if not post.post_id:
                    continue
                post_id = str(post.post_id)
                if post_id not in seen:
                    seen.add(post_id)
                    ids.append(post_id)
            if len(ids) >= needed:
                break
    return ids


def _delay_window(config_key: str) -> Tuple[float, float]:
    lo, hi = NTEConfig.get_config(config_key).data
    return float(lo), float(hi)


def _is_already_signed(error: TajiduoError) -> bool:
    return any(hint in error.message for hint in ("重复", "已签", "已经签到"))


def _format_app_rewards(result: CommunitySignResult) -> str:
    rewards: List[str] = []
    if result.exp:
        rewards.append(f"exp+{result.exp}")
    if result.gold_coin:
        rewards.append(f"金币+{result.gold_coin}")
    return " ".join(rewards)


def _fmt(label: str, status: str, extra: str = "") -> str:
    return f"{label}: {status}" + (f" {extra}" if extra else "")
