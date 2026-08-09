from __future__ import annotations

import time
import asyncio
from datetime import datetime

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.msgs import SignMsg, CommonMsg, send_nte_notify
from ..utils.session import SessionCall
from ..utils.database import NTESignResignRecord
from .sign_calendar_card import draw_sign_calendar_img
from ..nte_config.nte_config import NTEConfig
from ..utils.sdk.tajiduo_model import TajiduoError

TAG = "签到日历"

# 签到日历图内存缓存：2 分钟内同一角色重复查询直接秒回，跳过塔吉多接口和图片渲染。
_calendar_img_cache: dict[tuple[str, str, str], tuple[float, bytes]] = {}
CALENDAR_IMG_TTL_SECONDS = 120


def _calendar_cache_get(key: tuple[str, str, str]) -> bytes | None:
    item = _calendar_img_cache.get(key)
    if item is not None and time.time() - item[0] < CALENDAR_IMG_TTL_SECONDS:
        return item[1]
    return None


def _calendar_cache_set(key: tuple[str, str, str], data: bytes) -> None:
    _calendar_img_cache[key] = (time.time(), data)


async def run_sign_calendar(bot: Bot, ev: Event, game_id: str) -> None:
    async with SessionCall(
        bot,
        ev,
        tag=TAG,
        not_logged_in_msg=CommonMsg.not_logged_in(),
        login_expired_msg=SignMsg.login_expired(),
        load_failed_msg=SignMsg.CALENDAR_LOAD_FAILED,
        game_id=game_id,
    ) as session:
        if session is None:
            return
        user, client = session
        cache_key = (user.uid, game_id, datetime.now().strftime("%Y-%m-%d"))
        cached = _calendar_cache_get(cache_key)
        if cached is not None:
            return await bot.send(cached)
        state, rewards = await asyncio.gather(
            client.get_game_sign_state(game_id),
            client.get_game_sign_rewards(game_id),
        )
        if not rewards:
            return await send_nte_notify(bot, ev, SignMsg.CALENDAR_EMPTY)

        # 补签统计：可补签 = 上限 - 已用（服务端权威，本地流水兜底），
        # 与「补签信息」命令口径一致；漏签 = 今日天数 - 累计 - 今日未签时再减 1。
        limit = int(NTEConfig.get_config("NTESignResignLimit").data)
        used = await NTESignResignRecord.count_for_month(user.center_uid, game_id, datetime.now().strftime("%Y-%m"))
        used = max(used, state.re_sign_cnt)
        try:
            info = await client.get_game_sign_resign_info(game_id)
            used = max(used, info.re_sign_cnt)
            limit = info.re_sign_limit or limit
        except TajiduoError:
            pass
        resign_remaining = max(0, limit - used)
        missed_days = max(0, state.day - state.days - (0 if state.today_sign else 1))

        img = await draw_sign_calendar_img(
            ev,
            state,
            rewards,
            user.role_name,
            user.uid,
            game_id,
            resign_remaining=resign_remaining,
            missed_days=missed_days,
        )
        _calendar_cache_set(cache_key, img)
        await bot.send(img)
