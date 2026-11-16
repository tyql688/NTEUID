from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .adapters import archive_to_nte, tap_to_archive
from .gacha_card import draw_gacha_summary_img
from ..utils.msgs import GachaMsg, send_nte_notify
from .gacha_history import NTEGachaHistory
from ..utils.sdk.base import SdkError
from ..utils.sdk.taptap import taptap
from ..utils.sdk.taptap_model import TaptapError


async def send_tap_summary(
    bot: Bot,
    ev: Event,
    *,
    tap_id: int,
    history: NTEGachaHistory,
) -> None:
    """按 TapTap 返回的游戏 UID 合并本地记录并生成抽卡图片。"""
    try:
        binding = await taptap.check_binding(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] TapTap 查询失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)
    if not binding.is_bind:
        return await send_nte_notify(bot, ev, GachaMsg.TAPTAP_NOT_BOUND)

    try:
        tap_summary = await taptap.gacha_summary(tap_id)
    except SdkError as err:
        logger.warning(f"[NTE抽卡] TapTap 抽卡总览失败 user_id={ev.user_id} tap_id={tap_id} err={err.message}")
        return await send_nte_notify(bot, ev, GachaMsg.LOAD_FAILED)

    try:
        snapshot = tap_to_archive(binding.role_id, tap_summary)
    except TaptapError as err:
        logger.warning(f"[NTE抽卡] TapTap 记录转换失败: {err.message}")
        return await send_nte_notify(bot, ev, GachaMsg.TAPTAP_IMPORT_FAILED)

    archive = await history.merge(snapshot)
    summary = archive_to_nte(archive)
    if summary.is_empty:
        return await send_nte_notify(bot, ev, GachaMsg.empty(binding.name))

    img = await draw_gacha_summary_img(ev, summary, role_name=binding.name, role_id=archive.uid)
    await bot.send(img)


def _normalize_tap_id(arg: str) -> int | None:
    arg = arg.strip()
    return int(arg) if arg.isdigit() else None
