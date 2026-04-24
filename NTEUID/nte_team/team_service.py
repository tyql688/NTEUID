from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .team_card import draw_team_img
from ..utils.msgs import TeamMsg, send_nte_notify
from ..utils.session import ensure_tajiduo_client
from ..utils.database import NTEUser
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.sdk.tajiduo_model import TajiduoError, TeamRecommendation


def _filter_recommendations(
    recommendations: list[TeamRecommendation],
    std_char_name: str,
    char_id: str,
) -> list[TeamRecommendation]:
    result: list[TeamRecommendation] = []
    for recommendation in recommendations:
        recommendation_name = alias_to_char_name(recommendation.name)
        if recommendation_name is None:
            recommendation_name = recommendation.name
        if recommendation.id == char_id or recommendation_name == std_char_name:
            result.append(recommendation)
    return result


async def run_team(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, TeamMsg.USAGE_DETAIL)

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, TeamMsg.CHAR_NOT_FOUND)
    char_id = char_name_to_char_id(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, TeamMsg.CHAR_NOT_FOUND)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        return await send_nte_notify(bot, ev, TeamMsg.NOT_LOGGED_IN)

    try:
        client = await ensure_tajiduo_client(user)
    except TajiduoError as error:
        await NTEUser.mark_invalid_by_cookie(user.cookie, "refresh 失败")
        logger.warning(f"[NTE配队] 账号 {user.center_uid} 刷新失败: {error.message}")
        return await send_nte_notify(bot, ev, TeamMsg.LOGIN_EXPIRED)

    try:
        recs = await client.get_team_recommendations()
    except TajiduoError as error:
        logger.warning(f"[NTE配队] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, TeamMsg.LOAD_FAILED)

    if not recs:
        return await send_nte_notify(bot, ev, TeamMsg.EMPTY)

    matched = _filter_recommendations(recs, std_char_name, char_id)
    if not matched:
        return await send_nte_notify(bot, ev, TeamMsg.NO_RECOMMENDATION)

    await bot.send(await draw_team_img(matched, std_char_name))
