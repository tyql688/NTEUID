from __future__ import annotations

from datetime import timedelta

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.msgs import BindMsg, send_nte_notify
from ..utils.database import NTEUser
from ..utils.game_registry import GAME_LABELS


async def view_bindings(bot: Bot, ev: Event) -> None:
    rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
    if not rows:
        return await send_nte_notify(bot, ev, BindMsg.not_logged_in())

    grouped: dict[str, list[NTEUser]] = {}
    for row in rows:
        grouped.setdefault(row.center_uid, []).append(row)

    lines = [f"已绑定 {len(grouped)} 个塔吉多账号"]
    for idx, (center_uid, rs) in enumerate(grouped.items(), 1):
        lines.append(f"{idx}. 塔吉多账号 {center_uid}{'（当前）' if idx == 1 else ''}")
        lines += [f"   · {GAME_LABELS.get(r.game_id, r.game_id)} {r.role_name}（{r.uid}）" for r in rs]
    await send_nte_notify(bot, ev, "\n".join(lines))


async def switch_binding(bot: Bot, ev: Event, target: str) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if len(accounts) < 2:
        msg = BindMsg.not_logged_in() if not accounts else BindMsg.ONLY_ONE_ACCOUNT
        return await send_nte_notify(bot, ev, msg)

    center_uid = _resolve_target(target, accounts)
    if center_uid is None:
        return await send_nte_notify(bot, ev, BindMsg.target_not_found())

    # 无参轮换：把旧 head 踩到最老，N 个账号才能循环 A→B→C→A。
    if not target:
        await NTEUser.touch_account(
            ev.user_id,
            ev.bot_id,
            accounts[0].center_uid,
            when=accounts[-1].updated_at - timedelta(seconds=1),
        )
    await NTEUser.touch_account(ev.user_id, ev.bot_id, center_uid)
    await send_nte_notify(bot, ev, BindMsg.SWITCH_DONE.format(center_uid=center_uid))


async def get_laohu_tokens(bot: Bot, ev: Event) -> None:
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if not accounts:
        return await send_nte_notify(bot, ev, BindMsg.not_logged_in())

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


def _resolve_target(target: str, accounts: list[NTEUser]) -> str | None:
    """空→次新；纯数字≤账号数→按序号；否则精确匹配 center_uid。"""
    if not target:
        return accounts[1].center_uid
    if target.isdigit() and 1 <= int(target) <= len(accounts):
        return accounts[int(target) - 1].center_uid
    hit = next((a for a in accounts if a.center_uid == target), None)
    return hit.center_uid if hit else None
