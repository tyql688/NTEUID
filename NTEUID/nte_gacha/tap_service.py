from __future__ import annotations

from typing import Literal

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .adapters import tap_to_nte
from .gacha_card import draw_gacha_summary_img
from ..utils.msgs import GachaMsg, CommonMsg, send_nte_notify
from ..utils.database import NTEUser
from ..utils.sdk.base import SdkError
from ..utils.sdk.taptap import taptap

TapSummaryResult = Literal["sent", "not_bound", "failed", "empty"]


async def run_bind_tap(bot: Bot, ev: Event, tap_id_arg: str) -> None:
    if not tap_id_arg:
        return await send_nte_notify(bot, ev, GachaMsg.usage_bind())
    tap_id = _normalize_tap_id(tap_id_arg)
    if tap_id is None:
        return await send_nte_notify(bot, ev, GachaMsg.INVALID_TAP_ID)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        has_history = await NTEUser.has_logged_in_history(ev.user_id, ev.bot_id)
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in(has_history=has_history))

    tap_id_str = str(tap_id)
    if user.tap_id == tap_id_str:
        return await send_nte_notify(bot, ev, GachaMsg.BIND_ALREADY_SAME)

    try:
        binding = await taptap.check_binding(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] 绑定校验失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)

    if not binding.is_bind:
        return await send_nte_notify(bot, ev, GachaMsg.TAPTAP_NOT_BOUND)
    if binding.role_id != user.uid:
        return await send_nte_notify(
            bot,
            ev,
            GachaMsg.bind_role_mismatch(
                taptap_role_name=binding.name,
                nte_role_name=user.role_name,
            ),
        )

    await NTEUser.set_tap_id(user.center_uid, tap_id_str)
    logger.info(f"[NTE抽卡] TapTap 绑定成功 user_id={ev.user_id} center_uid={user.center_uid} tap_id={tap_id}")
    # 绑定成功后直接展示抽卡记录
    try:
        tap_summary = await taptap.gacha_summary(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] TapTap 抽卡总览失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)
    summary = tap_to_nte(tap_summary)
    role_name = binding.name or user.role_name or "TapTap 玩家"
    if summary.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(role_name))
    img = await draw_gacha_summary_img(ev, summary, role_name=role_name, role_id=binding.role_id or "")
    await bot.send(img)


async def send_tap_summary(
    bot: Bot,
    ev: Event,
    *,
    tap_id: int,
    fallback_role_name: str,
    silent_not_bound: bool = False,
) -> TapSummaryResult:
    try:
        binding = await taptap.check_binding(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] TapTap 查询失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)
        return "failed"
    if not binding.is_bind:
        if not silent_not_bound:
            await send_nte_notify(bot, ev, GachaMsg.TAPTAP_NOT_BOUND)
        return "not_bound"

    role_name = binding.name or fallback_role_name or "TapTap 玩家"

    try:
        tap_summary = await taptap.gacha_summary(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] TapTap 抽卡总览失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)
        return "failed"
    summary = tap_to_nte(tap_summary)
    if summary.is_empty:
        await send_nte_notify(bot, ev, GachaMsg.empty(role_name))
        return "empty"

    img = await draw_gacha_summary_img(ev, summary, role_name=role_name, role_id=binding.role_id or "")
    await bot.send(img)
    return "sent"


def _normalize_tap_id(arg: str) -> int | None:
    arg = arg.strip()
    return int(arg) if arg.isdigit() else None
