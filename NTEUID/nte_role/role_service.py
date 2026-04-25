from __future__ import annotations

from typing import Tuple, Optional

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from .role_card import draw_role_card_img
from .role_text import (
    format_vehicles,
    format_achievement,
    format_refresh_summary,
    format_character_detail,
)
from .role_cache import load_role_characters_cache, save_role_characters_cache
from ..utils.msgs import RoleMsg, send_nte_notify
from .explore_card import draw_explore_img
from .realtime_card import draw_realtime_img
from ..utils.session import ensure_tajiduo_client
from ..utils.database import NTEUser
from .realestate_card import draw_realestate_img
from ..utils.sdk.tajiduo import TajiduoClient
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..utils.sdk.tajiduo_model import TajiduoError, CharacterDetail


async def _ensure_ctx(bot: Bot, ev: Event, tag: str) -> Optional[Tuple[NTEUser, TajiduoClient, str]]:
    """走 `ensure_tajiduo_client`：DB 缓存未过 TTL 就零网络直接返回，否则 refresh 一次。
    返回 (user, client, role_id) 或 None（已发消息）。"""
    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        await send_nte_notify(bot, ev, RoleMsg.NOT_LOGGED_IN)
        return None

    try:
        client = await ensure_tajiduo_client(user)
    except TajiduoError as error:
        await NTEUser.mark_invalid_by_cookie(user.cookie, "refresh 失败")
        logger.warning(f"[NTE{tag}] 账号 {user.center_uid} 刷新失败: {error.message}")
        await send_nte_notify(bot, ev, RoleMsg.LOGIN_EXPIRED)
        return None

    return user, client, user.uid


async def run_role_home(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "角色面板")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        home = await client.get_role_home(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE角色面板] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    cached = await load_role_characters_cache(role_id)
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

    await bot.send(format_character_detail(target))


async def run_refresh_role_panel(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "刷新面板")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        raw_characters = await client.get_role_characters_data(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE刷新面板] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.REFRESH_FAILED)

    parsed_characters = [CharacterDetail.model_validate(item) for item in raw_characters]
    await save_role_characters_cache(role_id, raw_characters)

    await bot.send(format_refresh_summary(parsed_characters))


async def run_achievement(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "成就进度")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        achievement = await client.get_role_achievement_progress(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE成就进度] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    if not achievement.detail:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)

    await bot.send(format_achievement(achievement))


async def run_realestate(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "房产")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        houses = await client.get_role_realestate(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE房产] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    if not houses:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)

    await bot.send(await draw_realestate_img(ev, houses, user.role_name))


async def run_realtime(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "实时信息")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        home = await client.get_role_home(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE实时信息] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    await bot.send(await draw_realtime_img(ev, home, user.role_name))


async def run_explore(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "探索详情")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        areas = await client.get_role_area_progress(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE探索详情] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    if not areas:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)

    await bot.send(await draw_explore_img(ev, areas, user.role_name))


async def run_vehicles(bot: Bot, ev: Event) -> None:
    ctx = await _ensure_ctx(bot, ev, "载具")
    if ctx is None:
        return
    user, client, role_id = ctx

    try:
        vehicles = await client.get_role_vehicles(role_id)
    except TajiduoError as error:
        logger.warning(f"[NTE载具] 账号 {user.center_uid} 拉取失败: {error.message}")
        return await send_nte_notify(bot, ev, RoleMsg.LOAD_FAILED)

    if not vehicles.detail:
        return await send_nte_notify(bot, ev, RoleMsg.EMPTY)

    await bot.send(format_vehicles(vehicles))
