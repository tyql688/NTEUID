from __future__ import annotations

import json

from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .rank_card import RankEntry, draw_rank_img
from ..utils.msgs import RankMsg, CharacterMsg, send_nte_notify
from .panel_image import cache_original_image
from ..utils.avatar import fetch_avatar
from .character_card import draw_character_card_with_original
from ..utils.database import NTEUser, NTECharData, NTEGroupMember
from ..utils.name_convert import CHARS
from .strongest_board_card import BoardEntry, draw_strongest_board_img
from ..utils.sdk.tajiduo_model import CharacterDetail

MAX_ENTRIES = 20
MAX_BOARD = 60


async def _send_rank(
    bot: Bot,
    ev: Event,
    char_name: str,
    *,
    scope_label: str,
    uids: list[str] | None,
    group_identity: dict[str, tuple[str, str]] | None = None,
) -> None:
    """uids 给定 = 本群排名；为 None = bot排名。
    身份查询全部按集合大小封顶：本群直接用群表身份；全服只查"自己的 uid"(定位自己) +
    展示 ≤21 行的身份——绝不对全表 ranked 做 IN 反查（会撞 SQLite 变量上限且没必要）。
    """
    std_char_name = CHARS.name_of(char_name)
    char_id = CHARS.id_of(std_char_name) if std_char_name else None
    if not std_char_name or not char_id:
        return await send_nte_notify(bot, ev, CharacterMsg.NOT_FOUND)

    total = await NTECharData.count_for_char(char_id, uids)
    if total == 0:
        return await send_nte_notify(bot, ev, RankMsg.NO_SCORE)
    show = await NTECharData.rank_for_char(char_id, uids, limit=MAX_ENTRIES)

    if group_identity is not None:
        self_uids = {uid for uid, (owner, _) in group_identity.items() if owner == ev.user_id}
    else:
        self_uids = await NTEUser.uids_of_user(ev.user_id, ev.bot_id)

    need = [uid for uid, _, _ in show]
    overflow: tuple[int, tuple[str, int, str]] | None = None
    if self_uids and {uid for uid, _, _ in show}.isdisjoint(self_uids):
        self_row = await NTECharData.best_for_char(char_id, list(self_uids))
        if self_row is not None:
            self_rank = await NTECharData.rank_position_for_char(char_id, self_row[0], self_row[1], uids)
            if self_rank > MAX_ENTRIES:
                overflow = (self_rank, self_row)
    if overflow is not None:
        need.append(overflow[1][0])

    # 群排名身份来自群表；全服排名只查展示行（≤21）身份
    identity = group_identity if group_identity is not None else await NTEUser.identity_by_uids(need)
    details = await NTECharData.details_for(need, char_id)

    def build(row: tuple[str, int, str]) -> RankEntry:
        uid, score, grade = row
        user_id, role_name = identity[uid]
        char = CharacterDetail.model_validate(json.loads(details[uid]))
        suit = char.suit
        return RankEntry(
            user_id, role_name, uid, char.awaken_lev, suit.id, suit.name, suit.suit_activate_num, score, grade
        )

    shown = [build(row) for row in show]
    self_overflow = (overflow[0], build(overflow[1])) if overflow is not None else None
    await bot.send(await draw_rank_img(ev, std_char_name, char_id, shown, total, scope_label, self_overflow))


async def run_character_rank(bot: Bot, ev: Event, char_name: str) -> None:
    """本群评分排名：先取本群登记过的号，再按号查分。"""
    if not char_name:
        return await send_nte_notify(bot, ev, RankMsg.usage())
    if not ev.group_id:
        return await send_nte_notify(bot, ev, RankMsg.GROUP_ONLY)
    members = await NTEGroupMember.list_members(ev.group_id, ev.bot_id)
    if not members:
        return await send_nte_notify(bot, ev, RankMsg.NO_MEMBER)
    identity = {m.uid: (m.user_id, m.role_name) for m in members}
    await _send_rank(bot, ev, char_name, scope_label="本群", uids=list(identity), group_identity=identity)


async def run_bot_rank(bot: Bot, ev: Event, char_name: str) -> None:
    """bot评分排名：直接扫全表，不按群。"""
    if not char_name:
        return await send_nte_notify(bot, ev, RankMsg.usage_bot())
    await _send_rank(bot, ev, char_name, scope_label="bot", uids=None)


async def _scope_member_uids(bot: Bot, ev: Event, bot_scope: bool) -> tuple[bool, list[str] | None]:
    """最强面板/排行的作用域解析 → (ok, uids)。
    bot_scope=True → (True, None) 扫全表；否则校验群聊+成员，成功 (True, 群成员uid)，失败 (False, None) 并已发提示。
    """
    if bot_scope:
        return True, None
    if not ev.group_id:
        await send_nte_notify(bot, ev, RankMsg.GROUP_ONLY)
        return False, None
    members = await NTEGroupMember.list_members(ev.group_id, ev.bot_id)
    if not members:
        await send_nte_notify(bot, ev, RankMsg.NO_MEMBER)
        return False, None
    return True, [m.uid for m in members]


async def run_strongest_panel(bot: Bot, ev: Event, char_name: str, *, bot_scope: bool) -> None:
    """某角色评分最强账号的面板：bot_scope=全服第一，否则本群第一。头像走 fetch_avatar(同 bot排行)，持有账号本人。"""
    std_char_name = CHARS.name_of(char_name)
    char_id = CHARS.id_of(std_char_name) if std_char_name else None
    if not std_char_name or not char_id:
        return await send_nte_notify(bot, ev, CharacterMsg.NOT_FOUND)

    ok, uids = await _scope_member_uids(bot, ev, bot_scope)
    if not ok:
        return
    top = await NTECharData.best_for_char(char_id, uids)
    if top is None:
        return await send_nte_notify(bot, ev, RankMsg.NO_SCORE)

    top_uid = top[0]
    char = CharacterDetail.model_validate(json.loads((await NTECharData.details_for([top_uid], char_id))[top_uid]))
    user_id, role_name = (await NTEUser.identity_by_uids([top_uid]))[top_uid]
    avatar = await fetch_avatar(ev, user_id)
    img, original_img_path = await draw_character_card_with_original(char, role_name, top_uid, avatar)
    message_ids = await bot.send(MessageSegment.image(img), wait_recall=True)
    cache_original_image(message_ids, original_img_path)


async def run_strongest_board(bot: Bot, ev: Event, *, bot_scope: bool) -> None:
    """最强排行：每个角色取评分最强的号，按分降序。bot_scope=全服，否则本群。"""
    ok, uids = await _scope_member_uids(bot, ev, bot_scope)
    if not ok:
        return
    rows = await NTECharData.strongest_per_char(uids)
    if not rows:
        return await send_nte_notify(bot, ev, RankMsg.NO_SCORE)

    show = rows[:MAX_BOARD]
    identity = await NTEUser.identity_by_uids([uid for _, uid, _, _ in show])
    details = await NTECharData.details_for_pairs([(uid, char_id) for char_id, uid, _, _ in show])
    entries: list[BoardEntry] = []
    for char_id, uid, score, grade in show:
        char = CharacterDetail.model_validate(json.loads(details[(uid, char_id)]))
        _, holder_name = identity[uid]
        entries.append(
            BoardEntry(
                char_id=char_id,
                char_name=char.name,
                awaken_lev=char.awaken_lev,
                suit_id=char.suit.id,
                suit_name=char.suit.name,
                suit_pieces=char.suit.suit_activate_num,
                holder_name=holder_name,
                holder_uid=uid,
                score=score,
                grade=grade,
            )
        )
    await bot.send(await draw_strongest_board_img(entries, "BOT" if bot_scope else "本群"))
