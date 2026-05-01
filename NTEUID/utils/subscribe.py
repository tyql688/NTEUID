from __future__ import annotations

from gsuid_core.logger import logger
from gsuid_core.models import Event, Message
from gsuid_core.subscribe import gs_subscribe
from gsuid_core.utils.database.models import Subscribe

# NTEUID 用到的订阅 topic 集中声明，业务模块不要散落字符串。
TOPIC_NOTICE = "订阅NTE公告"
TOPIC_SIGN_PUSH = "订阅NTE自动签到"
TOPIC_SIGN_SUMMARY = "订阅NTE签到结果"


async def subscribe_single(topic: str, ev: Event) -> None:
    """同 user 全局唯一一条订阅；后开覆盖前开（要多群独立请用 `session`）。"""
    await gs_subscribe.add_subscribe("single", topic, ev)


async def unsubscribe_single(topic: str, ev: Event) -> int:
    return await Subscribe.delete_row(task_name=topic, user_id=ev.user_id, bot_id=ev.bot_id)


async def subscribe_session(topic: str, ev: Event, *, extra_message: str = "") -> bool:
    """同一个群只保留一条订阅；重复订阅会刷新发送路由。返回此前是否已存在。"""
    existed = await unsubscribe_session(topic, ev)
    await gs_subscribe.add_subscribe("session", topic, ev, extra_message=extra_message)
    return bool(existed)


async def unsubscribe_session(topic: str, ev: Event) -> int:
    if ev.group_id:
        return await Subscribe.delete_row(task_name=topic, group_id=ev.group_id)
    return await Subscribe.delete_row(task_name=topic, user_id=ev.user_id, bot_id=ev.bot_id)


async def list_subscribers(topic: str) -> list[Subscribe]:
    subs = await gs_subscribe.get_subscribe(topic)
    return list(subs) if subs else []


async def broadcast(topic: str, messages: Message | list[Message] | str | bytes) -> None:
    """同一份消息发给 topic 全员；单订阅失败只 warn 不传播。"""
    for sub in await list_subscribers(topic):
        try:
            await sub.send(messages)
        except Exception as error:
            logger.warning(f"[NTE订阅] {topic} 推送 user={sub.user_id} group={sub.group_id} 失败: {error!r}")
