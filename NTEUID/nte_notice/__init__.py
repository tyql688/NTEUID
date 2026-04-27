import random
import asyncio

from gsuid_core.sv import SV
from gsuid_core.aps import scheduler
from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.subscribe import gs_subscribe

from .notice import get_notice, get_all_notice_list
from ..utils.msgs import NoticeMsg, send_nte_notify
from .notice_card import draw_notice_detail_img
from ..utils.sdk.tajiduo import tajiduo_web
from ..nte_config.nte_config import NTEConfig
from ..utils.sdk.tajiduo_model import TajiduoError

sv_nte_notice = SV("nte公告")
sv_nte_notice_sub = SV("订阅NTE公告", pm=3)

TASK_NAME_NOTICE = "订阅NTE公告"
ANN_CHECK_MIN: int = NTEConfig.get_config("NTEAnnCheckMinutes").data


@sv_nte_notice.on_command("公告", block=True)
async def send_nte_notice(bot: Bot, ev: Event):
    await get_notice(bot, ev)


@sv_nte_notice_sub.on_fullmatch("订阅公告")
async def sub_nte_notice(bot: Bot, ev: Event):
    if not ev.group_id:
        return await send_nte_notify(bot, ev, NoticeMsg.SUBSCRIBE_GROUP_ONLY)
    if not NTEConfig.get_config("NTEAnnOpen").data:
        return await send_nte_notify(bot, ev, NoticeMsg.PUSH_CLOSED)

    data = await gs_subscribe.get_subscribe(TASK_NAME_NOTICE)
    if data and any(sub.group_id == ev.group_id for sub in data):
        return await send_nte_notify(bot, ev, NoticeMsg.ALREADY_SUBSCRIBED)

    await gs_subscribe.add_subscribe("session", TASK_NAME_NOTICE, ev, extra_message="")
    await send_nte_notify(bot, ev, NoticeMsg.SUBSCRIBED)


@sv_nte_notice_sub.on_fullmatch(("取消订阅公告", "退订公告"))
async def unsub_nte_notice(bot: Bot, ev: Event):
    if not ev.group_id:
        return await send_nte_notify(bot, ev, NoticeMsg.UNSUBSCRIBE_GROUP_ONLY)

    data = await gs_subscribe.get_subscribe(TASK_NAME_NOTICE)
    if data and any(sub.group_id == ev.group_id for sub in data):
        await gs_subscribe.delete_subscribe("session", TASK_NAME_NOTICE, ev)
        return await send_nte_notify(bot, ev, NoticeMsg.UNSUBSCRIBED)

    return await send_nte_notify(bot, ev, NoticeMsg.NOT_SUBSCRIBED)


@scheduler.scheduled_job("interval", minutes=ANN_CHECK_MIN)
async def check_nte_notice():
    if not NTEConfig.get_config("NTEAnnOpen").data:
        return
    await check_nte_notice_state()


async def check_nte_notice_state():
    logger.info("[异环公告] 定时任务: 异环公告查询..")
    subs = await gs_subscribe.get_subscribe(TASK_NAME_NOTICE)
    if not subs:
        logger.info("[异环公告] 暂无群订阅")
        return

    columns = await get_all_notice_list()
    flat = [post for posts in columns.values() for post in posts]
    if not flat:
        return

    known_ids: list[int] = NTEConfig.get_config("NTEAnnIds").data
    fresh_ids = [post.post_id for post in flat]

    if not known_ids:
        NTEConfig.set_config("NTEAnnIds", fresh_ids)
        logger.info("[异环公告] 初始成功, 将在下个轮询中更新.")
        return

    pending = [post for post in flat if post.post_id not in known_ids]
    if not pending:
        logger.info("[异环公告] 没有最新公告")
        return

    merged = sorted(set(known_ids) | set(fresh_ids), reverse=True)[:50]
    NTEConfig.set_config("NTEAnnIds", merged)

    for post in reversed(pending):
        try:
            detail = await tajiduo_web.get_notice_detail(post.post_id)
            img = await draw_notice_detail_img(detail)
        except TajiduoError as error:
            logger.warning(f"[异环公告] 拉取详情失败 postId={post.post_id}: {error}")
            continue

        for sub in subs:
            await sub.send(img)  # type: ignore
            await asyncio.sleep(random.uniform(1, 3))

    logger.info("[异环公告] 推送完毕")
