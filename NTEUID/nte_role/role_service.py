from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .role_card import draw_role_card_img
from .role_text import format_refresh_summary
from .role_cache import load_role_characters_cache, save_role_characters_cache
from ..utils.msgs import RoleMsg, send_nte_notify
from .explore_card import draw_explore_img
from .vehicle_card import draw_vehicle_img
from .realtime_card import draw_realtime_img
from ..utils.session import open_session, report_call_error
from .character_card import draw_character_card_img
from ..utils.database import NTEUser
from .realestate_card import draw_realestate_img
from .achievement_card import draw_achievement_img
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.sdk.tajiduo_model import TajiduoError, CharacterDetail


def _open(tag: str):
    """各 service 共用的 open_session 默认参数。"""
    return {
        "tag": tag,
        "not_logged_in_msg": RoleMsg.NOT_LOGGED_IN,
        "login_expired_msg": RoleMsg.LOGIN_EXPIRED,
    }


async def run_role_home(bot: Bot, ev: Event) -> None:
    tag = "角色面板"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        home = await client.get_role_home(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    cached = await load_role_characters_cache(user.uid)
    characters = [CharacterDetail.model_validate(item) for item in cached] if cached else []
    await bot.send(await draw_role_card_img(ev, home, characters, user.role_name))


async def run_character_detail(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, RoleMsg.USAGE_DETAIL)

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)
    char_id = char_name_to_char_id(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        return await send_nte_notify(bot, ev, RoleMsg.NOT_LOGGED_IN)

    cached = await load_role_characters_cache(user.uid)
    if not cached:
        return await send_nte_notify(bot, ev, RoleMsg.LOCAL_EMPTY)
    characters = [CharacterDetail.model_validate(item) for item in cached]

    target = next((character for character in characters if character.id == char_id), None)
    if target is None:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    await bot.send(await draw_character_card_img(ev, target, user.role_name))


async def run_refresh_role_panel(bot: Bot, ev: Event) -> None:
    tag = "刷新面板"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        raw_characters = await client.get_role_characters_data(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.REFRESH_FAILED,
        )
    parsed_characters = [CharacterDetail.model_validate(item) for item in raw_characters]
    await save_role_characters_cache(user.uid, raw_characters)
    await bot.send(format_refresh_summary(parsed_characters))


async def run_achievement(bot: Bot, ev: Event) -> None:
    tag = "成就进度"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        achievement = await client.get_role_achievement_progress(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    if not achievement.detail:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
    await bot.send(await draw_achievement_img(ev, achievement, user.role_name))


async def run_realestate(bot: Bot, ev: Event) -> None:
    tag = "房产"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        houses = await client.get_role_realestate(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    if not houses:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
    await bot.send(await draw_realestate_img(ev, houses, user.role_name))


async def run_realtime(bot: Bot, ev: Event) -> None:
    tag = "实时信息"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        home = await client.get_role_home(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    await bot.send(await draw_realtime_img(ev, home, user.role_name))


async def run_explore(bot: Bot, ev: Event) -> None:
    tag = "探索详情"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        areas = await client.get_role_area_progress(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    if not areas:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
    await bot.send(await draw_explore_img(ev, areas, user.role_name))


async def run_vehicles(bot: Bot, ev: Event) -> None:
    tag = "载具"
    session = await open_session(bot, ev, **_open(tag))
    if session is None:
        return
    user, client = session
    try:
        vehicles = await client.get_role_vehicles(user.uid)
    except TajiduoError as error:
        return await report_call_error(
            bot,
            ev,
            user,
            error,
            tag=tag,
            login_expired_msg=RoleMsg.LOGIN_EXPIRED,
            load_failed_msg=RoleMsg.LOAD_FAILED,
        )
    if not vehicles.detail:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
    await bot.send(await draw_vehicle_img(ev, vehicles, user.role_name))
