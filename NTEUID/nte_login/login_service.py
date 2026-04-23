from __future__ import annotations

import asyncio
import hashlib
from typing import List, Tuple, Optional
from pathlib import Path
from datetime import datetime
from dataclasses import dataclass

from gsuid_core.bot import Bot
from gsuid_core.config import core_config
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.cookie_manager.qrlogin import get_qrcode_base64

from ..utils.msgs import LoginMsg, send_nte_notify
from ..utils.cache import TimedCache
from ..utils.utils import get_public_ip
from ..utils.database import NTEUser
from ..utils.constants import LAOHU_APP_ID, LAOHU_APP_KEY
from ..utils.sdk.laohu import LaohuClient, LaohuDevice
from ..utils.sdk.tajiduo import TajiduoClient
from ..utils.game_registry import PRIMARY_GAME_ID, GAME_SIGN_SWITCHES
from ..nte_config.nte_config import NTEConfig
from ..utils.sdk.tajiduo_model import GameRoleList, TajiduoError

LOGIN_CACHE: TimedCache = TimedCache(timeout=600, maxsize=32)
LOGIN_WAIT_SECONDS = 600
LOGIN_POLL_INTERVAL = 2.0


@dataclass
class LoginState:
    user_id: str
    bot_id: str
    group_id: Optional[str]
    device: LaohuDevice
    status: str = "pending"  # pending | success | failed
    ok: bool = False
    msg: str = ""


@dataclass
class LoginResult:
    ok: bool
    msg: str = ""

    @classmethod
    def fail(cls, msg: str) -> "LoginResult":
        return cls(ok=False, msg=msg)

    @classmethod
    def success(cls, msg: str = "") -> "LoginResult":
        return cls(ok=True, msg=msg)


async def _login_page_url() -> str:
    url = NTEConfig.get_config("NTELoginUrl").data.strip()
    if url:
        return url if url.startswith("http") else f"https://{url}"

    host = core_config.get_config("HOST")
    port = core_config.get_config("PORT")
    if host in {"localhost", "127.0.0.1"}:
        host = "localhost"
    else:
        host = await get_public_ip(host)
    return f"http://{host}:{port}"


async def request_login(bot: Bot, ev: Event) -> None:
    auth_token = _auth_token(ev.user_id)
    login_url = f"{await _login_page_url()}/nte/i/{auth_token}"
    await _send_login_link(bot, ev, login_url)

    # 已有进行中的登录：复用同一个链接，不另开 wait 循环
    if LOGIN_CACHE.get(auth_token):
        return

    LOGIN_CACHE.set(
        auth_token,
        LoginState(
            user_id=ev.user_id,
            bot_id=ev.bot_id,
            group_id=ev.group_id,
            device=LaohuDevice(),
        ),
    )

    result = await _wait(auth_token)
    if result is None:
        return await send_nte_notify(bot, ev, LoginMsg.TIMEOUT)
    await send_nte_notify(bot, ev, result.msg)


def _auth_token(user_id: str) -> str:
    """按 user_id 生成稳定的登录 token，同一个 QQ 永远映射到同一个登录页。"""
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


async def send_login_sms(auth_token: str, mobile: str) -> LoginResult:
    state: Optional[LoginState] = LOGIN_CACHE.get(auth_token)
    if not state:
        return LoginResult.fail(LoginMsg.SESSION_EXPIRED)
    await LaohuClient(LAOHU_APP_ID, LAOHU_APP_KEY, device=state.device).send_sms_code(mobile)
    return LoginResult.success(msg=LoginMsg.SMS_SENT)


async def perform_login(auth_token: str, mobile: str, code: str) -> LoginResult:
    state: Optional[LoginState] = LOGIN_CACHE.get(auth_token)
    if not state:
        return LoginResult.fail(LoginMsg.SESSION_EXPIRED)

    laohu = LaohuClient(LAOHU_APP_ID, LAOHU_APP_KEY, device=state.device)
    account = await laohu.login_by_sms(mobile, code)
    tajiduo = TajiduoClient(device_id=state.device.device_id)
    tj_session = await tajiduo.user_center_login(account.token, str(account.user_id))
    roles = await _collect_all_roles(tajiduo)
    if not roles:
        mark_login_failed(auth_token, LoginMsg.NO_SUPPORTED_GAME)
        return LoginResult.fail(LoginMsg.NO_SUPPORTED_GAME)

    await NTEUser.sync_account_roles(
        user_id=state.user_id,
        bot_id=state.bot_id,
        center_uid=tj_session.center_uid,
        entries=roles,
        status="",
        dev_code=state.device.device_id,
        cookie=tj_session.refresh_token,
        access_token=tj_session.access_token,
        access_token_updated_at=datetime.now(),
        laohu_token=account.token,
        laohu_user_id=str(account.user_id),
    )

    state.status = "success"
    state.ok = True
    state.msg = LoginMsg.TAJIDUO_SUCCESS
    LOGIN_CACHE.set(auth_token, state)
    logger.info(
        f"[NTE登录] user_id={state.user_id} center_uid={tj_session.center_uid} "
        f"roles={[rid for rid, _, _ in roles]} 登录完成"
    )
    return LoginResult.success(msg=LoginMsg.TAJIDUO_SUCCESS)


async def _collect_all_roles(tajiduo: TajiduoClient) -> List[Tuple[str, str, str]]:
    """按注册表顺序把所有游戏的角色都拉一遍；塔吉多后端按 gameId 独立存储，
    互不覆盖。签到是否实际签某个游戏由签到编排层按开关决定，这里无条件全拉——
    开关拨动后不用重登/重刷就能立即生效。
    """
    collected: List[Tuple[str, str, str]] = []
    for game_id in GAME_SIGN_SWITCHES:
        collected.extend(await _collect_roles(tajiduo, game_id))
    return collected


async def _collect_roles(tajiduo: TajiduoClient, game_id: str) -> List[Tuple[str, str, str]]:
    """get_bind_role + get_game_roles 双路合并，按 roleId 去重，主绑定排第一。

    返回 (role_id, role_name, game_id) 三元组。game_id 由查询参数兜定——查的是什么游戏，
    落盘就是什么游戏，不依赖 API 返回体的 gameId 字段（存在性不稳定）。
    """
    collected: List[Tuple[str, str, str]] = []
    seen: set[str] = set()

    bind = await tajiduo.get_bind_role(game_id)
    if bind.uid:
        collected.append((bind.uid, bind.role_name.strip(), game_id))
        seen.add(bind.uid)

    extras = await tajiduo.get_game_roles(game_id)
    for item in extras.roles:
        if item.uid and item.uid not in seen:
            collected.append((item.uid, item.role_name.strip(), game_id))
            seen.add(item.uid)

    if game_id == PRIMARY_GAME_ID:
        await _ensure_bind_role(tajiduo, game_id, extras)
    return collected


async def _ensure_bind_role(tajiduo: TajiduoClient, game_id: str, roles: GameRoleList) -> None:
    """账号下还没设主绑定角色时自动绑第一个——为了顺手拿 `bind_role` 成就任务 70 金币。
    绑定失败不阻塞登录；下次登录还会再试一次。"""
    if roles.bind_role_id != 0 or not roles.roles:
        return
    first_role_id = roles.roles[0].uid
    if not first_role_id:
        return
    try:
        await tajiduo.bind_game_role(game_id, first_role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE登录] 自动绑定主角色失败 roleId={first_role_id}: {error.message}")
        return
    logger.info(f"[NTE登录] 自动绑定主角色 roleId={first_role_id}")


async def _send_login_link(bot: Bot, ev: Event, url: str) -> None:
    at_sender = bool(ev.group_id)
    forward = bool(NTEConfig.get_config("NTELoginForward").data)
    private_onebot = not ev.group_id and ev.bot_id == "onebot"

    if NTEConfig.get_config("NTEQRLogin").data:
        path = Path(__file__).parent / f"{ev.user_id}.gif"
        im = [
            f"[异环] 您的id为【{ev.user_id}】\n",
            LoginMsg.LINK_QR,
            MessageSegment.image(await get_qrcode_base64(url, path, ev.bot_id)),
        ]
        try:
            if forward and not private_onebot:
                await bot.send(MessageSegment.node(im))
            elif forward:
                await bot.send(im)
            else:
                await bot.send(im, at_sender=at_sender)
        finally:
            if path.exists():
                path.unlink()
        return

    if NTEConfig.get_config("NTETencentWord").data:
        url = f"https://docs.qq.com/scenario/link.html?url={url}"
    lines = [
        f"[异环] 您的id为【{ev.user_id}】",
        LoginMsg.LINK_COPY,
        f" {url}",
        LoginMsg.LINK_TTL,
    ]
    if forward and not private_onebot:
        await bot.send(MessageSegment.node(lines))
    else:
        await bot.send("\n".join(lines), at_sender=at_sender)


async def _wait(auth_token: str) -> Optional[LoginState]:
    waited = 0.0
    while waited < LOGIN_WAIT_SECONDS:
        state: Optional[LoginState] = LOGIN_CACHE.get(auth_token)
        if not state:
            return None
        if state.status in {"success", "failed"}:
            LOGIN_CACHE.pop(auth_token)
            return state
        await asyncio.sleep(LOGIN_POLL_INTERVAL)
        waited += LOGIN_POLL_INTERVAL
    LOGIN_CACHE.pop(auth_token)
    return None


async def refresh_all_user_tokens(user_id: str, bot_id: str) -> List[Tuple[str, bool, str]]:
    """按 center_uid 去重后，对每个账号各刷新一次 session。
    返回 [(center_uid, success, reason)]。reason 只在失败时有值。"""
    users = await NTEUser.list_latest_per_account(user_id, bot_id)
    logger.info(f"[NTE刷新令牌] user_id={user_id} bot_id={bot_id} 取到 {len(users)} 个账号")
    results: List[Tuple[str, bool, str]] = []
    for user in users:
        if not user.laohu_token or not user.laohu_user_id:
            results.append((user.center_uid, False, "登录信息不完整"))
            continue
        ok = await refresh_user_token(user)
        results.append((user.center_uid, ok, "" if ok else "凭证已失效"))
    return results


async def refresh_user_token(user: NTEUser) -> bool:
    """用库里存着的 laohu_token + laohu_user_id 直接重新走 user_center_login，
    拿一对全新 access_token / refresh_token 写回 DB。返回 True = 成功刷新。

    适用场景：refresh_token 死了（HTTP 402）但 laohu_token 还活着时，
    不用再发短信验证码就能把会话"续命"。注意：会把服务端同 center_uid 的
    其它活跃会话（比如手机 APP 那端）顶掉。"""
    if not user.laohu_token or not user.laohu_user_id:
        return False

    tajiduo = TajiduoClient(device_id=user.dev_code)
    try:
        session = await tajiduo.user_center_login(user.laohu_token, user.laohu_user_id)
    except TajiduoError as error:
        logger.warning(f"[NTE刷新令牌] 账号 {user.center_uid} 重新登录失败: {error.message}")
        return False

    await NTEUser.update_tokens(
        center_uid=session.center_uid,
        refresh_token=session.refresh_token,
        access_token=session.access_token,
    )

    # 顺带同步异环 + 幻塔角色，避免老用户打开幻塔签到开关后还得重登。
    # `user_center_login` 已把 access_token 写回 client 内部状态，可直接跑 authed 接口。
    # 角色同步失败不影响 refresh 成功语义——tokens 已经落库，下次签到会重试拉角色。
    try:
        roles = await _collect_all_roles(tajiduo)
        await NTEUser.sync_account_roles(
            user_id=user.user_id,
            bot_id=user.bot_id,
            center_uid=session.center_uid,
            entries=roles,
            status="",
            dev_code=user.dev_code,
            cookie=session.refresh_token,
            access_token=session.access_token,
            access_token_updated_at=datetime.now(),
            laohu_token=user.laohu_token,
            laohu_user_id=user.laohu_user_id,
        )
    except TajiduoError as error:
        logger.warning(f"[NTE刷新令牌] 账号 {session.center_uid} 角色同步失败: {error.message}")
        return True
    logger.info(f"[NTE刷新令牌] 账号 {session.center_uid} 已刷新，同步 {len(roles)} 个角色")
    return True


def mark_login_failed(auth_token: str, msg: str) -> None:
    state: Optional[LoginState] = LOGIN_CACHE.get(auth_token)
    if not state:
        return
    state.status = "failed"
    state.ok = False
    state.msg = msg
    LOGIN_CACHE.set(auth_token, state)
