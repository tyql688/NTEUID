from __future__ import annotations

from typing import Tuple, Optional
from datetime import datetime

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .msgs import send_nte_notify
from .database import NTEUser
from .constants import ACCESS_TOKEN_TTL_SECONDS
from .sdk.tajiduo import TajiduoClient
from .game_registry import PRIMARY_GAME_ID
from .sdk.tajiduo_model import TajiduoError

# 塔吉多业务接口在 session 被顶下/失效时返回 401/402/403；HTTP 状态在 SDK 层落到 `error.raw`
_AUTH_STATUSES = {401, 402, 403}


async def ensure_tajiduo_client(user: NTEUser) -> TajiduoClient:
    """返回带可用 access_token 的 client。DB 缓存未过 TTL 直接复用、零网络；
    超 TTL 或无缓存时调一次 refresh 并落库。refresh 失败的 TajiduoError 透传给调用方。"""
    client = TajiduoClient.from_user(user)
    if _access_token_fresh(user):
        client.access_token = user.access_token
        return client

    session = await client.refresh_session()
    await NTEUser.update_tokens(
        center_uid=user.center_uid,
        refresh_token=session.refresh_token,
        access_token=session.access_token,
    )
    return client


def _access_token_fresh(user: NTEUser) -> bool:
    if not user.access_token or user.access_token_updated_at is None:
        return False
    age = (datetime.now() - user.access_token_updated_at).total_seconds()
    return age < ACCESS_TOKEN_TTL_SECONDS


def is_auth_error(error: TajiduoError) -> bool:
    """`401/402/403` —— 塔吉多 App 端把这个 session 顶下/失效。
    业务层视作"需要重新登录"，而不是普通的"加载失败"。"""
    raw = error.raw
    return isinstance(raw, dict) and raw.get("status_code") in _AUTH_STATUSES


async def _pick_user(user_id: str, bot_id: str, game_id: str) -> Optional[NTEUser]:
    targets = await NTEUser.list_sign_targets_by_user(user_id, bot_id)
    return next((u for u in targets if u.game_id == game_id), None)


async def open_session(
    bot: Bot,
    ev: Event,
    *,
    tag: str,
    not_logged_in_msg: str,
    login_expired_msg: str,
    game_id: str = PRIMARY_GAME_ID,
) -> Optional[Tuple[NTEUser, TajiduoClient]]:
    """选活跃账号 + refresh client。返回 `(user, client)` 或 `None`（消息已发，调用方直接 `return`）。
    refresh 抛 `TajiduoError` 一律按 LOGIN_EXPIRED 处理（mark_invalid + 重登提示）。"""
    user = await _pick_user(ev.user_id, ev.bot_id, game_id)
    if user is None:
        await send_nte_notify(bot, ev, not_logged_in_msg)
        return None
    try:
        client = await ensure_tajiduo_client(user)
    except TajiduoError as error:
        await NTEUser.mark_invalid_by_cookie(user.cookie, "refresh 失败")
        logger.warning(f"[NTE{tag}] 账号 {user.center_uid} 刷新失败: {error.message}")
        await send_nte_notify(bot, ev, login_expired_msg)
        return None
    return user, client


async def report_call_error(
    bot: Bot,
    ev: Event,
    user: NTEUser,
    error: TajiduoError,
    *,
    tag: str,
    login_expired_msg: str,
    load_failed_msg: str,
) -> None:
    """业务接口抛 `TajiduoError` 时分流：
    - 401/402/403 → 视作 session 失效：mark_invalid + LOGIN_EXPIRED 重登提示
    - 其它 → LOAD_FAILED 普通加载失败提示"""
    if is_auth_error(error):
        await NTEUser.mark_invalid_by_cookie(user.cookie, "session 失效")
        logger.warning(f"[NTE{tag}] 账号 {user.center_uid} 会话失效: {error.message}")
        await send_nte_notify(bot, ev, login_expired_msg)
        return
    logger.warning(f"[NTE{tag}] 账号 {user.center_uid} 拉取失败: {error.message}")
    await send_nte_notify(bot, ev, load_failed_msg)
