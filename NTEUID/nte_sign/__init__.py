from datetime import datetime, timedelta

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.message import send_msg_to_master

from ..utils.msgs import SignMsg, send_nte_notify
from .sign_runner import (
    run_all_sign,
    run_user_sign,
    run_scheduled_sign,
)
from .sign_calendar import run_sign_calendar
from ..utils.database import NTEUser, NTESignRecord
from ..utils.constants import GAME_ID_HUANTA, GAME_ID_YIHUAN
from ..nte_config.nte_config import NTEConfig

sv_nte_sign = SV("nte签到")
sv_nte_sign_all = SV("nte全部签到", pm=1)
sv_nte_auto = SV("nte自动签到")
sv_nte_sign_calendar = SV("nte签到日历")


def _parse_sign_time() -> tuple[int, int]:
    raw = NTEConfig.get_config("NTESignTime").data
    try:
        if isinstance(raw, str):
            h, m = raw.split(":")
            hour, minute = int(h), int(m)
        else:
            hour, minute = int(raw[0]), int(raw[1])
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            return hour, minute
    except (ValueError, TypeError, IndexError):
        pass
    return 0, 30


_sign_hour, _sign_minute = _parse_sign_time()


@sv_nte_sign.on_fullmatch(("签到", "日签"))
async def nte_manual_sign(bot: Bot, ev: Event):
    await send_nte_notify(bot, ev, await run_user_sign(ev.user_id, ev.bot_id))


@sv_nte_sign_all.on_fullmatch("全部签到")
async def nte_all_sign(bot: Bot, ev: Event):
    result = await run_all_sign()
    if result is None:
        return await send_nte_notify(bot, ev, SignMsg.BATCH_BUSY)
    await bot.send(result)


@sv_nte_auto.on_fullmatch(("开启自动签到", "开启自动签"))
async def nte_enable_auto(bot: Bot, ev: Event):
    n = await NTEUser.set_auto_sign(ev.user_id, ev.bot_id, on=True)
    msg = f"{SignMsg.AUTO_ENABLED}（{n} 个账号）" if n else SignMsg.AUTO_NO_ACCOUNT
    await send_nte_notify(bot, ev, msg)


@sv_nte_auto.on_fullmatch(("关闭自动签到", "关闭自动签"))
async def nte_disable_auto(bot: Bot, ev: Event):
    n = await NTEUser.set_auto_sign(ev.user_id, ev.bot_id, on=False)
    msg = f"{SignMsg.AUTO_DISABLED}（{n} 个账号）" if n else SignMsg.AUTO_NO_ACCOUNT
    await send_nte_notify(bot, ev, msg)


@sv_nte_sign_calendar.on_fullmatch(("签到日历", "每日签到", "签到一览", "签到记录", "签到历史"))
async def nte_sign_calendar_yihuan(bot: Bot, ev: Event):
    await run_sign_calendar(bot, ev, GAME_ID_YIHUAN)


@sv_nte_sign_calendar.on_fullmatch(("幻塔签到日历", "幻塔每日签到", "幻塔签到一览", "幻塔签到记录", "幻塔签到历史"))
async def nte_sign_calendar_huanta(bot: Bot, ev: Event):
    await run_sign_calendar(bot, ev, GAME_ID_HUANTA)


@scheduler.scheduled_job("cron", hour=_sign_hour, minute=_sign_minute)
async def nte_scheduled_sign():
    if not NTEConfig.get_config("NTESignDaily").data:
        return
    logger.info("[NTE签到] 定时任务开始")
    summary = await run_scheduled_sign()
    if summary is None:
        logger.info(f"[NTE签到] {SignMsg.BATCH_SCHEDULE_BUSY}")
        return
    logger.info(f"[NTE签到] 定时任务完成: {summary}")
    if NTEConfig.get_config("NTESignMaster").data:
        await send_msg_to_master(summary)


@scheduler.scheduled_job("cron", hour=0, minute=10, id="nte_purge_sign_records")
async def nte_purge_sign_records():
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    purged = await NTESignRecord.purge_before(cutoff)
    if purged:
        logger.info(f"[NTE签到] 清理 7 天前签到记录 {purged} 条")
