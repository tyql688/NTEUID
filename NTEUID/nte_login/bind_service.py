from __future__ import annotations

from datetime import timedelta

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.msgs import TITLE, BindMsg, CommonMsg, send_nte_notify
from ..utils.database import NTEUser
from ..utils.sdk.tajiduo import TajiduoClient
from ..utils.msgs.buttons import switch_buttons, switched_buttons
from ..utils.game_registry import GAME_LABELS
from ..utils.sdk.tajiduo_model import TajiduoError


async def view_bindings(bot: Bot, ev: Event) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if not accounts:
        has_history = await NTEUser.has_logged_in_history(ev.user_id, ev.bot_id)
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in(has_history=has_history))

    grouped: dict[str, list[NTEUser]] = {}
    rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
    for row in rows:
        grouped.setdefault(row.center_uid, []).append(row)

    lines = [f"已绑定 {len(accounts)} 个塔吉多账号"]
    for idx, account in enumerate(accounts, 1):
        lines.append(f"{idx}. 塔吉多账号 {account.center_uid}{'（当前）' if idx == 1 else ''}")
        rs = grouped.get(account.center_uid, [])
        if not rs:
            lines.append("   · 角色信息暂未同步")
            continue
        lines += [f"   · {GAME_LABELS.get(r.game_id, r.game_id)} {r.role_name}（{r.uid}）" for r in rs]
    msg = "\n".join(lines)
    if len(accounts) < 2:
        await send_nte_notify(bot, ev, msg)
    else:
        await bot.send_option(f"{TITLE}{msg}", switch_buttons(), at_sender=bool(ev.group_id))


async def switch_binding(bot: Bot, ev: Event, target: str) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if len(accounts) < 2:
        msg = CommonMsg.not_logged_in() if not accounts else BindMsg.ONLY_ONE_ACCOUNT
        return await send_nte_notify(bot, ev, msg)

    account = _resolve_target(target, accounts)
    if account is None:
        return await send_nte_notify(bot, ev, BindMsg.target_not_found())

    # 无参轮换：把旧 head 踩到最老，N 个账号才能循环 A→B→C→A。
    if not target:
        await NTEUser.touch_account(
            ev.user_id,
            ev.bot_id,
            accounts[0].center_uid,
            when=accounts[-1].updated_at - timedelta(seconds=1),
        )
    await NTEUser.touch_account(ev.user_id, ev.bot_id, account.center_uid)
    msg = BindMsg.switch_done(account.center_uid, account.role_name, account.uid)
    await bot.send_option(f"{TITLE}{msg}", switched_buttons(), at_sender=bool(ev.group_id))


async def get_laohu_tokens(bot: Bot, ev: Event) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if not accounts:
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in())

    lines: list[str] = []
    for a in accounts:
        if not a.laohu_token or not a.laohu_user_id:
            continue
        lines += [
            f"塔吉多账号: {a.center_uid}",
            "laohuToken,laohuUserId:",
            f"{a.laohu_token},{a.laohu_user_id}",
            "--------------------------------",
        ]
    if not lines:
        return await send_nte_notify(bot, ev, BindMsg.TOKEN_EMPTY)
    await send_nte_notify(bot, ev, "\n".join(lines))


async def get_access_tokens(bot: Bot, ev: Event) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if not accounts:
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in())

    lines: list[str] = []
    for account in accounts:
        if not account.access_token:
            continue
        client = TajiduoClient.from_user(account)
        client.access_token = account.access_token
        try:
            info = await client.get_user_full_info()
        except TajiduoError:
            continue
        if info.center_uid != account.center_uid:
            continue
        lines += [
            f"塔吉多账号: {account.center_uid}",
            "accessToken:",
            account.access_token,
            "--------------------------------",
        ]
    if not lines:
        return await send_nte_notify(bot, ev, BindMsg.TOKEN_EMPTY)
    await send_nte_notify(bot, ev, "\n".join(lines))


def _resolve_target(target: str, accounts: list[NTEUser]) -> NTEUser | None:
    """空→次新；纯数字≤账号数→按序号；否则精确匹配 center_uid。"""
    if not target:
        return accounts[1]
    if target.isdigit() and 1 <= int(target) <= len(accounts):
        return accounts[int(target) - 1]
    return next((a for a in accounts if a.center_uid == target), None)
