import re

from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from . import login_router
from ..utils.msgs import LoginMsg, CommonMsg, send_nte_notify
from .bind_service import view_bindings, switch_binding, get_laohu_tokens, get_access_tokens
from .login_service import request_login, login_by_laohu_token, login_by_access_token, refresh_all_user_tokens
from ..utils.database import NTEUser, NTECharData, NTEGroupMember
from ..utils.game_registry import PRIMARY_GAME_ID

_ = login_router  # 纯副作用 import：FastAPI 路由在模块加载时注册

sv_nte_login = SV("nte登录")
sv_nte_bind = SV("nte绑定")
sv_nte_get_token = SV("nte获取laohutoken", area="DIRECT")
sv_nte_get_access_token = SV("nte获取accesstoken", area="DIRECT")


@sv_nte_login.on_command(("登录", "登陆", "login"))
async def nte_login_cmd(bot: Bot, ev: Event):
    text = re.sub(r'["\n\t ]+', "", ev.text.strip())
    text = text.replace("，", ",")

    if text == "":
        return await request_login(bot, ev)

    tokens = text.split(",")
    if len(tokens) == 2:
        left, right = tokens
        if len(left) == 32 and right.isdigit() and len(right) == 9:
            return await login_by_laohu_token(bot, ev, left, right)
        return await send_nte_notify(bot, ev, LoginMsg.USER_CENTER_LOGIN_FAILED)

    if len(tokens) == 1 and len(text) >= 40:
        return await login_by_access_token(bot, ev, text)

    return await send_nte_notify(bot, ev, LoginMsg.USER_CENTER_LOGIN_FAILED)


@sv_nte_login.on_fullmatch(("退出登录", "退出登陆", "登出", "logout"))
async def nte_logout_cmd(bot: Bot, ev: Event):
    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
        if not accounts:
            has_history = await NTEUser.has_logged_in_history(ev.user_id, ev.bot_id)
            return await send_nte_notify(bot, ev, CommonMsg.not_logged_in(has_history=has_history))
        user = accounts[0]

    # 只清理当前 center_uid 下异环角色的 uid
    all_rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
    uids = [r.uid for r in all_rows if r.uid and r.center_uid == user.center_uid and r.game_id == PRIMARY_GAME_ID]

    deleted = await NTEUser.delete_by_center_uid(ev.user_id, ev.bot_id, user.center_uid)
    if not deleted:
        return await send_nte_notify(bot, ev, LoginMsg.NOT_LOGGED_IN)

    await NTECharData.delete_by_uids(uids)
    await NTEGroupMember.delete_by_uids(ev.bot_id, uids)
    logger.info(f"[NTE登出] 清理角色数据 uids={uids}")

    await send_nte_notify(bot, ev, LoginMsg.LOGOUT_DONE)


@sv_nte_login.on_fullmatch(("全部登出", "退出全部登录", "退出全部登陆"))
async def nte_logout_all_cmd(bot: Bot, ev: Event):
    rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
    uids = [r.uid for r in rows if r.uid and r.game_id == PRIMARY_GAME_ID]

    deleted = await NTEUser.delete_all(ev.user_id, ev.bot_id)
    if not deleted:
        return await send_nte_notify(bot, ev, LoginMsg.NOT_LOGGED_IN)

    await NTECharData.delete_by_uids(uids)
    await NTEGroupMember.delete_by_uids(ev.bot_id, uids)
    logger.info(f"[NTE登出] 清理全部角色数据 uids={uids}")

    await send_nte_notify(bot, ev, LoginMsg.LOGOUT_ALL_DONE)


@sv_nte_get_token.on_fullmatch(
    ("获取laohutoken", "获取laohuToken", "获取LAOHUTOKEN", "获取laohu令牌"),
    block=True,
)
async def nte_get_token_cmd(bot: Bot, ev: Event):
    await get_laohu_tokens(bot, ev)


@sv_nte_get_access_token.on_fullmatch(
    ("获取accesstoken", "获取accessToken", "获取AccessToken", "获取ACCESS_TOKEN", "获取access_token"),
    block=True,
)
async def nte_get_access_token_cmd(bot: Bot, ev: Event):
    await get_access_tokens(bot, ev)


@sv_nte_bind.on_command(("切换", "查看"), block=True)
async def nte_bind_cmd(bot: Bot, ev: Event):
    target = re.sub(r'["\n\t ]+', "", ev.text.strip())

    if "查看" in ev.command:
        return await view_bindings(bot, ev)
    return await switch_binding(bot, ev, target)


@sv_nte_login.on_fullmatch(("刷新令牌", "刷新token", "续签"))
async def nte_refresh_token_cmd(bot: Bot, ev: Event):
    results = await refresh_all_user_tokens(ev.user_id, ev.bot_id)
    if not results:
        return await send_nte_notify(bot, ev, LoginMsg.REFRESH_NO_ACCOUNT)
    ok = sum(1 for _, success, _ in results if success)
    lines = [f"已刷新 {ok} / {len(results)} 个塔吉多账号"]
    for center_uid, success, reason in results:
        mark = "✅" if success else "❌"
        line = f"  · {mark} {center_uid}"
        if reason:
            line += f"（{reason}）"
        lines.append(line)
    await send_nte_notify(bot, ev, "\n".join(lines))
