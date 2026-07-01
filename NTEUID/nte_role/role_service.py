from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.at import AtTarget, resolve_at_target
from .role_card import draw_role_card_img
from .level_card import draw_level_img
from ..utils.msgs import TITLE, RoleMsg, CharacterMsg, send_nte_notify
from .panel_image import cache_original_image
from .explore_card import draw_explore_img
from .refresh_card import draw_refresh_img
from .vehicle_card import draw_vehicle_img
from .realtime_card import draw_realtime_img
from ..utils.session import SessionCall
from .character_card import draw_character_card_with_original
from .character_sort import diff_characters, sort_characters
from ..utils.database import NTEUser, NTEGroupMember
from .character_cache import (
    has_character_cache,
    load_character_cache,
    save_character_cache,
    load_character_detail_cache,
)
from .realestate_card import draw_realestate_img
from .achievement_card import draw_achievement_img
from ..utils.msgs.buttons import (
    login_buttons,
    relogin_buttons,
    role_home_buttons,
    refresh_changed_buttons,
)
from ..utils.name_convert import CHARS
from ..utils.sdk.tajiduo_model import CharacterDetail


def _session_call(bot: Bot, ev: Event, target: AtTarget, *, tag: str, load_failed_msg: str) -> SessionCall:
    return SessionCall(
        bot,
        ev,
        tag=tag,
        target_user_id=target.user_id,
        not_logged_in_msg=RoleMsg.not_logged_in(target.is_other),
        login_expired_msg=RoleMsg.login_expired(target.is_other),
        load_failed_msg=load_failed_msg,
    )


async def _load_cached_characters(bot: Bot, ev: Event) -> tuple[NTEUser, list[CharacterDetail]] | None:
    """解析 @目标 → 取活跃账号 → 读本地角色缓存；任一步缺数据发提示并返回 None。"""
    active = await _load_active_user(bot, ev)
    if active is None:
        return None
    user, target = active
    characters = await load_character_cache(user.uid)
    if not characters:
        await send_nte_notify(bot, ev, CharacterMsg.OTHER_LOCAL_EMPTY if target.is_other else CharacterMsg.LOCAL_EMPTY)
        return None
    return user, characters


async def _load_active_user(bot: Bot, ev: Event) -> tuple[NTEUser, AtTarget] | None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return None
    user = await NTEUser.get_active(target.user_id, ev.bot_id)
    if user is None:
        has_history = await NTEUser.has_logged_in_history(target.user_id, ev.bot_id)
        buttons = None if target.is_other else (relogin_buttons() if has_history else login_buttons())
        msg = RoleMsg.not_logged_in(target.is_other, has_history=has_history)
        if buttons is None:
            await send_nte_notify(bot, ev, msg)
        else:
            await bot.send_option(f"{TITLE}{msg}", buttons, at_sender=bool(ev.group_id))
        return None
    return user, target


async def run_role_home(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="角色面板", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        characters = await load_character_cache(user.uid)
        img = await draw_role_card_img(ev, home, characters, user.role_name)
        await bot.send_option(MessageSegment.image(img), role_home_buttons())


async def run_character_detail(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, CharacterMsg.usage_detail())

    std_char_name = CHARS.name_of(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, CharacterMsg.NOT_FOUND)
    char_id = CHARS.id_of(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, CharacterMsg.NOT_FOUND)

    active = await _load_active_user(bot, ev)
    if active is None:
        return
    user, target = active
    char = await load_character_detail_cache(user.uid, char_id)
    if char is None:
        if not await has_character_cache(user.uid):
            return await send_nte_notify(
                bot, ev, CharacterMsg.OTHER_LOCAL_EMPTY if target.is_other else CharacterMsg.LOCAL_EMPTY
            )
        return await send_nte_notify(bot, ev, CharacterMsg.NOT_FOUND)

    img, original_img_path = await draw_character_card_with_original(
        char, user.role_name, user.uid, await get_event_avatar(ev)
    )
    message_ids = await bot.send(MessageSegment.image(img), wait_recall=True)
    cache_original_image(message_ids, original_img_path)


async def run_character_level(bot: Bot, ev: Event) -> None:
    loaded = await _load_cached_characters(bot, ev)
    if loaded is None:
        return
    user, characters = loaded
    await bot.send(await draw_level_img(ev, user.role_name, user.uid, characters))


async def run_refresh_role_panel(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="刷新面板", load_failed_msg=RoleMsg.REFRESH_FAILED) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        raw_characters = await client.get_role_characters_data(user.uid)
        parsed_characters = [CharacterDetail.model_validate(item) for item in raw_characters]
        old_characters = await load_character_cache(user.uid)
        changed_ids = diff_characters(parsed_characters, old_characters)
        await save_character_cache(user.uid, raw_characters)
        # 群成员登记只在「自己在群里刷新」时做：upsert 用 ev.user_id(请求者) 绑 user.uid，@他人会错绑
        if ev.group_id and not target.is_other:
            await NTEGroupMember.upsert_member(ev.group_id, ev.bot_id, ev.user_id, user.uid, user.role_name)
        sorted_characters = sort_characters(parsed_characters, changed_ids=changed_ids)
        img = await draw_refresh_img(ev, user.role_name, user.uid, home, sorted_characters, len(changed_ids))
        changed_names = [
            name for ch in sorted_characters if ch.id in changed_ids and (name := CHARS.name_by_id(ch.id)) is not None
        ]
        await bot.send_option(MessageSegment.image(img), refresh_changed_buttons(changed_names))


async def run_achievement(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="成就进度", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        achievement = await client.get_role_achievement_progress(user.uid)
        if not achievement.detail:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_achievement_img(ev, achievement, user.role_name, user.uid))


async def run_realestate(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="房产", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        houses = await client.get_role_realestate(user.uid)
        if not houses:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_realestate_img(ev, houses, user.role_name, user.uid))


async def run_realtime(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="实时信息", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        home = await client.get_role_home(user.uid)
        avatar = await get_event_avatar(ev)
        await bot.send(await draw_realtime_img(avatar, user, home))


async def run_explore(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="探索详情", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        areas = await client.get_role_area_progress(user.uid)
        if not areas:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_explore_img(ev, areas, user.role_name, user.uid))


async def run_vehicles(bot: Bot, ev: Event) -> None:
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    async with _session_call(bot, ev, target, tag="载具", load_failed_msg=RoleMsg.LOAD_FAILED) as session:
        if session is None:
            return
        user, client = session
        vehicles = await client.get_role_vehicles(user.uid)
        if not vehicles.detail:
            return await send_nte_notify(bot, ev, RoleMsg.EMPTY)
        await bot.send(await draw_vehicle_img(ev, vehicles, user.role_name, user.uid))
