from __future__ import annotations

from datetime import datetime
from typing import Any

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.msgs import ResignMsg, send_nte_notify
from ..utils.session import SessionCall
from ..utils.database import NTEUser, NTESignResignRecord
from ..utils.game_registry import GAME_LABELS
from ..utils.sdk.tajiduo_model import TajiduoError
from ..nte_config.nte_config import NTEConfig
from .sign_runner import account_lock

TAG = "补签"


def _month() -> str:
    return datetime.now().strftime("%Y-%m")


def _resolve_role(users: list[NTEUser], query: str) -> NTEUser | None:
    """角色解析，逻辑对齐参考插件：空参数取该账号第一个角色；
    带参数先按 roleId 精确匹配，再按角色名包含匹配；匹配不到返回 None。"""
    if not users:
        return None
    q = (query or "").strip()
    if not q:
        return users[0]
    if q.isdigit():
        for user in users:
            if user.uid == q:
                return user
        return None
    for user in users:
        if q in user.role_name or user.role_name in q:
            return user
    return None


async def run_user_resign(bot: Bot, ev: Event, game_id: str, role_query: str = "") -> None:
    """执行单角色游戏补签。仅操作当前激活账号（该游戏下 updated_at 最新的一行）。"""
    game_label = GAME_LABELS[game_id]
    async with SessionCall(
        bot,
        ev,
        tag=TAG,
        not_logged_in_msg=ResignMsg.usage(game_label),
        login_expired_msg=ResignMsg.usage(game_label),
        load_failed_msg=ResignMsg.FAILED,
        game_id=game_id,
    ) as session:
        if session is None:
            return
        user, client = session

        targets = await NTEUser.list_sign_targets_by_user(user.user_id, user.bot_id)
        game_users = [u for u in targets if u.game_id == game_id and u.center_uid == user.center_uid]
        role = _resolve_role(game_users, role_query)
        if role is None:
            return await send_nte_notify(bot, ev, ResignMsg.role_not_found(game_label))

        lock = account_lock(user.center_uid)
        if lock.locked():
            return await send_nte_notify(bot, ev, ResignMsg.busy())
        async with lock:
            await _do_resign(bot, ev, user, client, role, game_id)


async def _do_resign(bot: Bot, ev: Event, user: NTEUser, client: Any, role: NTEUser, game_id: str) -> None:
    limit = int(NTEConfig.get_config("NTESignResignLimit").data)
    cost = int(NTEConfig.get_config("NTESignResignCost").data)
    month = _month()

    try:
        state = await client.get_game_sign_state(game_id)
    except TajiduoError as error:
        logger.warning(f"[NTE{TAG}] 账号 {user.center_uid} 补签前查状态失败: {error.message}")
        return await send_nte_notify(bot, ev, ResignMsg.FAILED)

    if not state.today_sign:
        return await send_nte_notify(bot, ev, ResignMsg.not_signed_today())
    if state.days >= state.day:
        return await send_nte_notify(bot, ev, ResignMsg.no_missed())

    # 本地兜底限流：以本地流水为准（服务端 resignCnt 为已用次数，仅用于展示）
    local_used = await NTESignResignRecord.count_for_month(user.center_uid, game_id, month)
    if local_used >= limit:
        return await send_nte_notify(bot, ev, ResignMsg.no_quota(local_used, limit))

    # 补签信息接口（官方 H5 同款）：校验呗果余额，避免发起必然失败的请求
    used = local_used
    coin: int | None = None
    try:
        info = await client.get_game_sign_resign_info(game_id)
        used = max(used, info.re_sign_cnt)
        coin = info.coin
        cost = info.cost or cost
        limit = info.re_sign_limit or limit
    except TajiduoError:
        pass
    if used >= limit:
        return await send_nte_notify(bot, ev, ResignMsg.no_quota(used, limit))
    if coin is not None and coin < cost:
        return await send_nte_notify(bot, ev, ResignMsg.coin_not_enough(cost))

    try:
        data = await client.game_sign_resign(role.uid, game_id)
    except TajiduoError as error:
        if _already_resigned_hint(error):
            return await send_nte_notify(bot, ev, ResignMsg.ALREADY_DONE)
        if _quota_hint(error):
            return await send_nte_notify(bot, ev, ResignMsg.no_quota(used, limit))
        if "不足" in error.message:
            return await send_nte_notify(bot, ev, ResignMsg.coin_not_enough(cost))
        logger.warning(f"[NTE{TAG}] 账号 {user.center_uid} 角色 {role.uid} 补签失败: {error.message}")
        return await send_nte_notify(bot, ev, ResignMsg.FAILED)

    await NTESignResignRecord.record(
        user.center_uid,
        game_id,
        role.uid,
        month,
        payload={"roleId": role.uid, "gameId": game_id, "raw": data},
    )
    used = await NTESignResignRecord.count_for_month(user.center_uid, game_id, month)
    reward = _extract_reward(data)
    await send_nte_notify(
        bot,
        ev,
        ResignMsg.done(role.role_name, role.uid, cost, used, limit, reward=reward),
    )


async def run_resign_info(bot: Bot, ev: Event, game_id: str) -> None:
    """查看本月补签信息（只读，不扣费）。"""
    game_label = GAME_LABELS[game_id]
    async with SessionCall(
        bot,
        ev,
        tag=TAG,
        not_logged_in_msg=ResignMsg.usage(game_label),
        login_expired_msg=ResignMsg.usage(game_label),
        load_failed_msg=ResignMsg.FAILED,
        game_id=game_id,
    ) as session:
        if session is None:
            return
        user, client = session
        state = await client.get_game_sign_state(game_id)
        limit = int(NTEConfig.get_config("NTESignResignLimit").data)
        cost = int(NTEConfig.get_config("NTESignResignCost").data)
        month = _month()
        local_used = await NTESignResignRecord.count_for_month(user.center_uid, game_id, month)
        # 服务端 reSignCnt 语义未实测前，展示取本地与服务端较大者，防止低估已用次数
        used = max(local_used, state.re_sign_cnt)

        coin: int | None = None
        try:
            info = await client.get_game_sign_resign_info(game_id)
            coin = info.coin
            cost = info.cost or cost
            used = max(used, info.re_sign_cnt)
            limit = info.re_sign_limit or limit
        except TajiduoError:
            # 服务端未开放 resign-info 接口时静默降级，用 state + 配置展示
            pass

        await send_nte_notify(
            bot,
            ev,
            ResignMsg.info(
                game_label,
                today_sign=state.today_sign,
                days=state.days,
                day=state.day,
                used=used,
                limit=limit,
                cost=cost,
                coin=coin,
            ),
        )


def _already_resigned_hint(error: TajiduoError) -> bool:
    return any(hint in error.message for hint in ("重复", "已补签", "补签过", "已经补签"))


def _quota_hint(error: TajiduoError) -> bool:
    return any(hint in error.message for hint in ("次数", "上限", "用完", "额度", "已用"))


def _extract_reward(data: dict) -> str:
    """尝试从补签返回里挑出奖励摘要；拿不到就留空。"""
    for key in ("reward", "message", "msg"):
        value = data.get(key)
        if isinstance(value, str) and value and "成功" not in value:
            return value
    return ""
