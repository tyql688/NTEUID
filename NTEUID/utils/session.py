from __future__ import annotations

import asyncio
from types import TracebackType
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

# 同 center_uid 并发 refresh 的 single-flight 表：首笔真跑、落库，后到的协程 await 同一 future。
# TTL 内的缓存命中不进这张表；只有真要打网络的才有竞争。
_refresh_inflight: dict[str, "asyncio.Future[tuple[str, str]]"] = {}


async def ensure_tajiduo_client(user: NTEUser) -> TajiduoClient:
    """返回带可用 access_token 的 client。DB 缓存未过 TTL 直接复用、零网络；
    超 TTL 或无缓存时调一次 refresh 并落库。同 center_uid 并发场景由
    single-flight 合并：第一笔真跑，后到协程复用同一 future 的结果，
    避免第二笔拿旧 refresh_token 撞 401/402 把账号误标失效。

    注意：`TajiduoClient.from_user` 只带 refresh_token，本函数会按需把 access_token
    回写到 client 实例字段（缓存路径直接 mutate；refresh 路径用 single-flight 拿到的
    最新 token 回写）——这是与 `from_user` 配对使用的约定。
    """
    client = TajiduoClient.from_user(user)
    if _access_token_fresh(user):
        client.access_token = user.access_token
        return client

    access_token, refresh_token = await _refresh_singleflight(user, client)
    client.access_token = access_token
    client.refresh_token = refresh_token
    return client


async def _refresh_singleflight(user: NTEUser, client: TajiduoClient) -> Tuple[str, str]:
    """同 center_uid 并发：首笔真跑 refresh + 落库，后到的协程 await 同一 future。
    异常（含 CancelledError）也会传递给所有等待者，避免 hang。"""
    inflight = _refresh_inflight.get(user.center_uid)
    if inflight is not None:
        return await inflight

    fut: "asyncio.Future[tuple[str, str]]" = asyncio.get_running_loop().create_future()
    _refresh_inflight[user.center_uid] = fut
    try:
        session = await client.refresh_session()
        await NTEUser.update_tokens(
            center_uid=session.center_uid,
            refresh_token=session.refresh_token,
            access_token=session.access_token,
        )
        result = (session.access_token, session.refresh_token)
        fut.set_result(result)
        return result
    except BaseException as exc:
        if not fut.done():
            fut.set_exception(exc)
        raise
    finally:
        _refresh_inflight.pop(user.center_uid, None)


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


async def refresh_or_invalidate(user: NTEUser, tag: str) -> Optional[TajiduoClient]:
    """`ensure_tajiduo_client` + refresh 失败兜底：mark_invalid + 警告日志，
    返回 None 让调用方按 LOGIN_EXPIRED 提示用户。不发用户消息，交给调用方决定。"""
    try:
        return await ensure_tajiduo_client(user)
    except TajiduoError as error:
        await NTEUser.mark_invalid_by_cookie(user.cookie, "refresh 失败")
        logger.warning(f"[NTE{tag}] 账号 {user.center_uid} 刷新失败: {error.message}")
        return None


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
    client = await refresh_or_invalidate(user, tag)
    if client is None:
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


class SessionCall:
    """`open_session` + 业务调用 `TajiduoError` 兜底合一的 async cm。

    `__aenter__` 返回 `None` 表示未登录或 refresh 失败（用户提示已发，body 直接 `return`）；
    返回 `(user, client)` 时 body 内若抛 `TajiduoError`，`__aexit__` 走
    `report_call_error` 按 401/402/403 → LOGIN_EXPIRED、其它 → LOAD_FAILED 分流并吞掉
    （返回 True 抑制异常）。其它异常照常传播。"""

    def __init__(
        self,
        bot: Bot,
        ev: Event,
        *,
        tag: str,
        not_logged_in_msg: str,
        login_expired_msg: str,
        load_failed_msg: str,
        game_id: str = PRIMARY_GAME_ID,
    ) -> None:
        self._bot = bot
        self._ev = ev
        self._tag = tag
        self._not_logged_in_msg = not_logged_in_msg
        self._login_expired_msg = login_expired_msg
        self._load_failed_msg = load_failed_msg
        self._game_id = game_id
        self._user: Optional[NTEUser] = None

    async def __aenter__(self) -> Optional[Tuple[NTEUser, TajiduoClient]]:
        session = await open_session(
            self._bot,
            self._ev,
            tag=self._tag,
            not_logged_in_msg=self._not_logged_in_msg,
            login_expired_msg=self._login_expired_msg,
            game_id=self._game_id,
        )
        if session is None:
            return None
        self._user, _ = session
        return session

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc: Optional[BaseException],
        tb: Optional[TracebackType],
    ) -> bool:
        if isinstance(exc, TajiduoError) and self._user is not None:
            await report_call_error(
                self._bot,
                self._ev,
                self._user,
                exc,
                tag=self._tag,
                login_expired_msg=self._login_expired_msg,
                load_failed_msg=self._load_failed_msg,
            )
            return True
        return False
