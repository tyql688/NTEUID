from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.msgs import GachaMsg, CommonMsg, send_nte_notify
from .tap_service import send_tap_summary, _normalize_tap_id
from .xhh_service import send_xhh_summary, send_xhh_summary_by_pkey
from ..utils.database import NTEUser
from ..utils.sdk.xiaoheihe import extract_heybox_id_from_pkey
from ..nte_config.nte_config import NTEConfig


async def _run_unsafe_gacha(bot: Bot, ev: Event, query: str) -> None:
    tap_id = _normalize_tap_id(query)
    if tap_id is not None:
        result = await send_tap_summary(bot, ev, tap_id=tap_id, fallback_role_name="", silent_not_bound=True)
        if result == "not_bound":
            return await send_nte_notify(bot, ev, GachaMsg.TAPTAP_NOT_BOUND)
        return

    if extract_heybox_id_from_pkey(query):
        return await send_xhh_summary_by_pkey(bot, ev, pkey=query)

    return await send_nte_notify(bot, ev, GachaMsg.INVALID_GACHA_QUERY_ID)


async def run_my_gacha(bot: Bot, ev: Event, query: str = "") -> None:
    query = query.strip()
    if query and bool(NTEConfig.get_config("NTEGachaUnsafeQuery").data):
        return await _run_unsafe_gacha(bot, ev, query)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        has_history = await NTEUser.has_logged_in_history(ev.user_id, ev.bot_id)
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in(has_history=has_history))

    # 优先 TapTap
    if user.tap_id:
        tap_id = _normalize_tap_id(user.tap_id)
        if tap_id is not None:
            await send_tap_summary(bot, ev, tap_id=tap_id, fallback_role_name=user.role_name)
            return
        logger.warning(f"[NTE抽卡] DB 中 tap_id 非数字 user_id={ev.user_id} tap_id={user.tap_id!r}")

    # fallback 小黑盒
    if user.xhh_pkey:
        return await send_xhh_summary(bot, ev, user)

    return await send_nte_notify(bot, ev, GachaMsg.bind_required())
