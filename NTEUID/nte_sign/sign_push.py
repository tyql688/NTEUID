from __future__ import annotations

from dataclasses import dataclass

from gsuid_core.logger import logger
from gsuid_core.models import Message
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.database.models import Subscribe

from .sign_runner import PerUserSignReport
from .sign_push_card import draw_sign_push_title
from ..utils.subscribe import TOPIC_SIGN_PUSH, list_subscribers
from ..nte_config.nte_config import NTEConfig


async def push_sign_reports(reports: list[PerUserSignReport]) -> None:
    """私聊发详细文本，群发汇总标题（图或文字）。"""
    if not reports:
        return

    push_private = NTEConfig.get_config("NTESignPushPrivate").data
    push_group = NTEConfig.get_config("NTESignPushGroup").data
    push_pic = NTEConfig.get_config("NTESignPushPic").data

    by_user: dict[tuple[str, str], PerUserSignReport] = {(r.user_id, r.bot_id): r for r in reports}
    group_buckets: dict[tuple[str, str, str, str], _GroupBucket] = {}

    for sub in await list_subscribers(TOPIC_SIGN_PUSH):
        report = by_user.get((sub.user_id, sub.bot_id))
        if report is None:
            continue
        if sub.user_type == "group" and sub.group_id:
            if not push_group:
                continue
            route_key = (sub.bot_id, sub.group_id, sub.bot_self_id, sub.WS_BOT_ID or "")
            bucket = group_buckets.setdefault(route_key, _GroupBucket(sub=sub))
            bucket.add(report)
        else:
            if not push_private:
                continue
            try:
                await sub.send([MessageSegment.text(report.text)])
            except Exception as error:
                logger.warning(f"[NTE签到] 私聊推送 user={sub.user_id} 失败: {error!r}")

    for (_, gid, _, _), bucket in group_buckets.items():
        try:
            messages = await bucket.render(push_pic=push_pic)
            if not messages:
                continue
            await bucket.sub.send(messages)
        except Exception as error:
            logger.warning(f"[NTE签到] 群推送 group={gid} 失败: {error!r}")


@dataclass
class _GroupBucket:
    """同群多用户聚合：只累计成功 / 失败计数，最后渲染一条群消息。"""

    sub: Subscribe
    success: int = 0
    failed: int = 0

    def add(self, r: PerUserSignReport) -> None:
        if r.has_failure:
            self.failed += 1
        else:
            self.success += 1

    async def render(self, *, push_pic: bool) -> list[Message]:
        if self.success == 0 and self.failed == 0:
            return []
        if push_pic:
            try:
                return [MessageSegment.image(await draw_sign_push_title(self.success, self.failed))]
            except Exception as error:
                logger.warning(f"[NTE签到] 标题图绘制失败，回退纯文本: {error!r}")
        return [MessageSegment.text(_text_title(self.success, self.failed))]


def _text_title(success: int, failed: int) -> str:
    return f"[异环] 今日自动签到任务已完成\n本群成功 {success} 人 · 失败 {failed} 人"
