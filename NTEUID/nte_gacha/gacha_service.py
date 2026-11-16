from __future__ import annotations

import time

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .adapters import archive_to_nte, tjd_to_archive
from ..utils.at import resolve_at_target
from .gacha_card import draw_gacha_summary_img
from ..utils.msgs import GachaMsg, send_nte_notify
from .tap_service import send_tap_summary, _normalize_tap_id
from .xhh_service import send_xhh_summary_by_pkey
from .gacha_history import NTEGachaHistory
from ..utils.session import report_call_error, ensure_tajiduo_client
from ..utils.database import NTEUser
from ..utils.sdk.xiaoheihe import extract_heybox_id_from_pkey
from ..utils.sdk.tajiduo_model import TajiduoError
from ..utils.resource.RESOURCE_PATH import GACHA_PATH

_history = NTEGachaHistory(GACHA_PATH)


async def run_my_gacha(bot: Bot, ev: Event, query: str = "") -> None:
    query = query.strip()
    if query:
        return await _run_direct_query(bot, ev, query)
    await _run_tajiduo(bot, ev)


async def _run_direct_query(bot: Bot, ev: Event, query: str) -> None:
    tap_id = _normalize_tap_id(query)
    if tap_id is not None:
        await send_tap_summary(bot, ev, tap_id=tap_id, history=_history)
        return
    if extract_heybox_id_from_pkey(query):
        await send_xhh_summary_by_pkey(bot, ev, pkey=query, history=_history)
        return
    await send_nte_notify(bot, ev, GachaMsg.INVALID_QUERY)


async def _run_tajiduo(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    user = await NTEUser.get_active(target.user_id, ev.bot_id, include_invalid=True)
    if user is None:
        has_history = await NTEUser.has_logged_in_history(target.user_id, ev.bot_id)
        return await send_nte_notify(bot, ev, GachaMsg.not_logged_in(target.is_other, has_history=has_history))

    failure_msg = GachaMsg.login_expired(target.is_other)
    try:
        client = await ensure_tajiduo_client(user)
        failure_msg = GachaMsg.LOAD_FAILED
        response = await client.get_gacha_summary()
        if response.roleid != user.uid:
            raise TajiduoError("抽卡记录 UID 与当前角色不一致")
        snapshot = tjd_to_archive(user.uid, response.gachaDetails, int(time.time()))
    except TajiduoError as error:
        archive = await _history.load(user.uid)
        if archive is None or archive.is_empty:
            return await report_call_error(
                bot,
                ev,
                user,
                error,
                tag="抽卡记录",
                login_expired_msg=GachaMsg.login_expired(target.is_other),
                load_failed_msg=failure_msg,
            )
        logger.warning(f"[NTE抽卡] UID={user.uid} 拉取失败，使用本地记录: {error.message}")
    else:
        archive = await _history.merge(snapshot)

    summary = archive_to_nte(archive)
    if summary.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(user.role_name))
    img = await draw_gacha_summary_img(ev, summary, role_name=user.role_name, role_id=user.uid)
    await bot.send(img)
