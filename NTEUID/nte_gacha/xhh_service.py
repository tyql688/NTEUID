from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .adapters import xhh_to_nte
from .gacha_card import draw_gacha_summary_img
from ..utils.msgs import GachaMsg, CommonMsg, XhhBindMsg, send_nte_notify
from ..utils.database import NTEUser
from ..utils.sdk.xiaoheihe import XiaoheiheClient
from ..utils.sdk.xiaoheihe_model import XiaoheiheError


async def run_bind_xhh(bot: Bot, ev: Event, pkey: str) -> None:
    pkey = pkey.strip()
    if not pkey:
        return await send_nte_notify(bot, ev, XhhBindMsg.usage_bind())
    if len(pkey) < 20:
        return await send_nte_notify(bot, ev, XhhBindMsg.INVALID_PKEY)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        has_history = await NTEUser.has_logged_in_history(ev.user_id, ev.bot_id)
        return await send_nte_notify(bot, ev, CommonMsg.not_logged_in(has_history=has_history))

    if user.xhh_pkey == pkey:
        return await send_nte_notify(bot, ev, XhhBindMsg.BIND_ALREADY_SAME)
    if user.xhh_pkey:
        logger.info(f"[NTE小黑盒] 换绑操作 user_id={ev.user_id}")

    client = XiaoheiheClient(pkey=pkey)
    try:
        analysis = await client.lottery_analysis()
    except XiaoheiheError as err:
        logger.warning(f"[NTE小黑盒] 绑定校验失败 user_id={ev.user_id}: {err.message}")
        if "重新登录" in err.message or "relogin" in err.message:
            return await send_nte_notify(bot, ev, XhhBindMsg.PKEY_EXPIRED)
        return await send_nte_notify(bot, ev, XhhBindMsg.VERIFY_FAILED)

    if not analysis.is_bind:
        return await send_nte_notify(bot, ev, XhhBindMsg.NOT_BOUND)

    # 角色一致性校验（如果小黑盒返回了 uid）
    if analysis.header_info.uid and analysis.header_info.uid != user.uid:
        return await send_nte_notify(
            bot,
            ev,
            XhhBindMsg.bind_role_mismatch(
                xhh_role_name=analysis.header_info.name or "未知",
                nte_role_name=user.role_name,
            ),
        )

    await NTEUser.set_xhh_bind(user.center_uid, pkey)
    logger.info(f"[NTE小黑盒] 绑定成功 user_id={ev.user_id} center_uid={user.center_uid}")
    # 绑定成功后直接展示抽卡记录
    if analysis.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(analysis.header_info.name or user.role_name))
    summary = xhh_to_nte(analysis)
    role_name = analysis.header_info.name or user.role_name or "小黑盒玩家"
    role_id = analysis.header_info.uid or user.uid or ""
    img = await draw_gacha_summary_img(ev, summary, role_name=role_name, role_id=role_id)
    await bot.send(img)


async def send_xhh_summary(bot: Bot, ev: Event, user: NTEUser) -> None:
    client = XiaoheiheClient(pkey=user.xhh_pkey)
    try:
        analysis = await client.lottery_analysis()
    except XiaoheiheError as err:
        logger.warning(f"[NTE抽卡] 小黑盒查询失败 user_id={ev.user_id} err={err.message}")
        if "重新登录" in err.message or "relogin" in err.message:
            return await send_nte_notify(bot, ev, GachaMsg.XHH_PKEY_EXPIRED)
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)

    if not analysis.is_bind:
        return await send_nte_notify(bot, ev, GachaMsg.XHH_NOT_BOUND)
    if analysis.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(analysis.header_info.name or user.role_name))

    summary = xhh_to_nte(analysis)
    role_name = analysis.header_info.name or user.role_name or "小黑盒玩家"
    role_id = analysis.header_info.uid or user.uid or ""
    img = await draw_gacha_summary_img(ev, summary, role_name=role_name, role_id=role_id)
    await bot.send(img)


async def send_xhh_summary_by_pkey(
    bot: Bot,
    ev: Event,
    *,
    pkey: str,
) -> None:
    client = XiaoheiheClient(pkey=pkey)
    try:
        analysis = await client.lottery_analysis()
    except XiaoheiheError as err:
        logger.warning(f"[NTE抽卡] 小黑盒 user_key 直查失败 user_id={ev.user_id} err={err.message}")
        if "重新登录" in err.message or "relogin" in err.message:
            return await send_nte_notify(bot, ev, GachaMsg.XHH_PKEY_EXPIRED)
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)

    if not analysis.is_bind:
        return await send_nte_notify(bot, ev, GachaMsg.XHH_TARGET_NOT_BOUND)
    role_name = analysis.header_info.name or "小黑盒玩家"
    if analysis.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(role_name))

    summary = xhh_to_nte(analysis)
    role_id = analysis.header_info.uid or ""
    img = await draw_gacha_summary_img(ev, summary, role_name=role_name, role_id=role_id)
    await bot.send(img)
