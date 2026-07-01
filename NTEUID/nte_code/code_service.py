from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.msgs import send_nte_notify
from ..utils.sdk.htnews import HtNewsError, ht_news


async def run_code(bot: Bot, ev: Event) -> None:
    try:
        items = await ht_news.fetch_code_list()
    except HtNewsError as err:
        logger.warning(f"[NTE兑换码] 拉取失败: {err.message}")
        return await send_nte_notify(bot, ev, "获取兑换码失败，请稍后再试")

    msgs = []
    for code in items:
        if code.is_fail == "1":
            continue
        if not code.order:
            continue
        msgs.append("\n".join([f"兑换码: {code.order}", f"奖励: {code.reward}", code.label]))

    await bot.send(msgs)
