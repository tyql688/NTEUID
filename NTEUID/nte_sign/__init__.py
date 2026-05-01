from datetime import datetime, timedelta

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .sign_push import push_sign_reports
from ..utils.msgs import SignMsg, send_nte_notify
from .sign_runner import (
    run_all_sign,
    run_user_sign,
    run_scheduled_sign,
)
from .sign_calendar import run_sign_calendar
from ..utils.database import NTEUser, NTESignRecord
from ..utils.constants import GAME_ID_HUANTA, GAME_ID_YIHUAN
from ..utils.subscribe import (
    TOPIC_SIGN_PUSH,
    TOPIC_SIGN_SUMMARY,
    broadcast,
    subscribe_single,
    unsubscribe_single,
)
from ..utils.game_registry import GAME_LABELS, disabled_sign_games
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
    summary, reports = result
    await bot.send(summary)
    await push_sign_reports(reports)
    await broadcast(TOPIC_SIGN_SUMMARY, summary)


def _format_auto_msg(header: str, changed: dict[str, int]) -> str:
    if not changed:
        return SignMsg.AUTO_NO_ACCOUNT
    lines = [f"- {GAME_LABELS.get(gid, gid)}：{n} 个角色" for gid, n in changed.items()]
    return f"{header}\n" + "\n".join(lines)


@sv_nte_auto.on_fullmatch(("开启自动签到", "开启自动签"))
async def nte_enable_auto(bot: Bot, ev: Event):
    if not NTEConfig.get_config("NTESignDaily").data:
        logger.info("[NTE签到] 定时签到总开关已关闭")
        return await send_nte_notify(bot, ev, SignMsg.AUTO_DAILY_DISABLED)
    if not await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id):
        return await send_nte_notify(bot, ev, SignMsg.not_logged_in())
    changed = await NTEUser.set_auto_sign(
        ev.user_id,
        ev.bot_id,
        on=True,
        exclude_game_ids=disabled_sign_games(),
    )
    if changed:
        await subscribe_single(TOPIC_SIGN_PUSH, ev)
    await send_nte_notify(bot, ev, _format_auto_msg(SignMsg.AUTO_ENABLED, changed))


@sv_nte_auto.on_fullmatch(("关闭自动签到", "关闭自动签"))
async def nte_disable_auto(bot: Bot, ev: Event):
    changed = await NTEUser.set_auto_sign(ev.user_id, ev.bot_id, on=False)
    removed = await unsubscribe_single(TOPIC_SIGN_PUSH, ev)
    if changed:
        msg = _format_auto_msg(SignMsg.AUTO_DISABLED, changed)
    else:
        msg = SignMsg.AUTO_DISABLED if removed else SignMsg.AUTO_NO_ACCOUNT
    await send_nte_notify(bot, ev, msg)


@sv_nte_sign_all.on_fullmatch(("订阅签到结果", "订阅签到汇总"))
async def nte_sub_sign_summary(bot: Bot, ev: Event):
    await subscribe_single(TOPIC_SIGN_SUMMARY, ev)
    await send_nte_notify(bot, ev, "已订阅签到结果汇总，每日定时签到完成后会推送")


@sv_nte_sign_all.on_fullmatch(("取消订阅签到结果", "取消订阅签到汇总"))
async def nte_unsub_sign_summary(bot: Bot, ev: Event):
    removed = await unsubscribe_single(TOPIC_SIGN_SUMMARY, ev)
    msg = "已取消订阅签到结果" if removed else "未订阅签到结果，无需取消"
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
    result = await run_scheduled_sign()
    if result is None:
        logger.info(f"[NTE签到] {SignMsg.BATCH_SCHEDULE_BUSY}")
        return
    summary, reports = result
    logger.info(f"[NTE签到] 定时任务完成: {summary}")
    await push_sign_reports(reports)
    await broadcast(TOPIC_SIGN_SUMMARY, summary)


@scheduler.scheduled_job("cron", hour=0, minute=10, id="nte_purge_sign_records")
async def nte_purge_sign_records():
    cutoff = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
    purged = await NTESignRecord.purge_before(cutoff)
    if purged:
        logger.info(f"[NTE签到] 清理 7 天前签到记录 {purged} 条")
