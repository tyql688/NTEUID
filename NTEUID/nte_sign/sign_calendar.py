from __future__ import annotations

import asyncio

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.at import resolve_at_target
from ..utils.msgs import SignMsg, send_nte_notify
from ..utils.session import SessionCall
from .sign_calendar_card import draw_sign_calendar_img
from ..utils.sdk.tajiduo_model import TajiduoError

TAG = "签到日历"

# 游戏固定规则：每账号每月最多 3 次补签。已用次数 / 上限由服务端「补签信息」接口
# 权威返回（剩余 = 上限 - 已用），该常量仅作接口不可用时的兜底。
RESIGN_MONTHLY_LIMIT = 3


async def run_sign_calendar(bot: Bot, ev: Event, game_id: str) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with SessionCall(
        bot,
        ev,
        tag=TAG,
        target_user_id=target.user_id,
        not_logged_in_msg=SignMsg.not_logged_in(is_other=target.is_other),
        login_expired_msg=SignMsg.login_expired(is_other=target.is_other),
        load_failed_msg=SignMsg.CALENDAR_LOAD_FAILED,
        game_id=game_id,
    ) as session:
        if session is None:
            return
        user, client = session
        state, rewards = await asyncio.gather(
            client.get_game_sign_state(game_id),
            client.get_game_sign_rewards(game_id),
        )
        if not rewards:
            return await send_nte_notify(bot, ev, SignMsg.CALENDAR_EMPTY)

        # 可补签次数 = 补签信息接口的「上限 - 已用」，实时查询不缓存；
        # 接口不可用时用签到状态接口的已用次数 + 固定上限兜底。
        try:
            info = await client.get_game_sign_resign_info(game_id)
            resign_remaining = max(0, info.re_sign_limit - info.re_sign_cnt)
        except TajiduoError:
            resign_remaining = max(0, RESIGN_MONTHLY_LIMIT - state.re_sign_cnt)
        # 漏签 = 本月总天数 - 累计签到 - 今日未签时再减 1（不计今日）。
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
        await bot.send(img)
