from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .role_card import draw_role_card_img
from .role_sort import diff_characters, sort_characters
from .role_cache import load_role_characters_cache, save_role_characters_cache
from ..utils.msgs import RoleMsg, send_nte_notify
from .explore_card import draw_explore_img
from .refresh_card import draw_refresh_img
from .vehicle_card import draw_vehicle_img
from .realtime_card import draw_realtime_img
from ..utils.session import SessionCall
from .character_card import draw_character_card_img
from ..utils.database import NTEUser
from .realestate_card import draw_realestate_img
from .achievement_card import draw_achievement_img
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.sdk.tajiduo_model import CharacterDetail


async def run_role_home(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="角色面板",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        characters = await load_role_characters_cache(user.uid)
        await bot.send(await draw_role_card_img(ev, home, characters, user.role_name))


async def run_character_detail(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, RoleMsg.usage_detail())

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)
    char_id = char_name_to_char_id(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        return await send_nte_notify(bot, ev, RoleMsg.not_logged_in())

    characters = await load_role_characters_cache(user.uid)
    if not characters:
        return await send_nte_notify(bot, ev, RoleMsg.LOCAL_EMPTY)

    target = next((character for character in characters if character.id == char_id), None)
    if target is None:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    await bot.send(await draw_character_card_img(ev, target, user.role_name, user.uid))


async def run_refresh_role_panel(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="刷新面板",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.REFRESH_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        raw_characters = await client.get_role_characters_data(user.uid)
        parsed_characters = [CharacterDetail.model_validate(item) for item in raw_characters]
        old_characters = await load_role_characters_cache(user.uid)
        changed_ids = diff_characters(parsed_characters, old_characters)
        await save_role_characters_cache(user.uid, raw_characters)
        sorted_characters = sort_characters(parsed_characters, changed_ids=changed_ids)
        await bot.send(await draw_refresh_img(ev, user.role_name, user.uid, home, sorted_characters, len(changed_ids)))


async def run_achievement(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="成就进度",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        achievement = await client.get_role_achievement_progress(user.uid)
        if not achievement.detail:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_achievement_img(ev, achievement, user.role_name, user.uid))


async def run_realestate(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="房产",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        houses = await client.get_role_realestate(user.uid)
        if not houses:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_realestate_img(ev, houses, user.role_name, user.uid))


async def run_realtime(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="实时信息",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        await bot.send(await draw_realtime_img(ev, user, home))


async def run_explore(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="探索详情",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        areas = await client.get_role_area_progress(user.uid)
        if not areas:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_explore_img(ev, areas, user.role_name, user.uid))


async def run_vehicles(bot: Bot, ev: Event) -> None:
    async with SessionCall(
        bot,
        ev,
        tag="载具",
        not_logged_in_msg=RoleMsg.not_logged_in(),
        login_expired_msg=RoleMsg.login_expired(),
        load_failed_msg=RoleMsg.LOAD_FAILED,
    ) as session:
        if session is None:
            return
        user, client = session
        vehicles = await client.get_role_vehicles(user.uid)
        if not vehicles.detail:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_vehicle_img(ev, vehicles, user.role_name, user.uid))
