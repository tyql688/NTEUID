from __future__ import annotations

from ..utils.sdk.tajiduo_model import CharacterDetail


def diff_characters(
    new_chars: list[CharacterDetail],
    old_chars: list[CharacterDetail],
) -> set[str]:
    """返回相对上次发生 alev / awaken_lev 变化（含全新）的 char.id；old_chars 为空表示首次跑，全部都算更新。"""
    if not old_chars:
        return {ch.id for ch in new_chars}
    old_map = {ch.id: (ch.alev, ch.awaken_lev) for ch in old_chars}
    return {ch.id for ch in new_chars if old_map.get(ch.id) != (ch.alev, ch.awaken_lev)}


def sort_characters(
    characters: list[CharacterDetail],
    *,
    changed_ids: set[str] | None = None,
) -> list[CharacterDetail]:
    """品级 → alev → 觉醒 → id 倒排；`changed_ids` 给了就在最前面再加一档『已更新优先』。"""

    def key(ch: CharacterDetail) -> tuple[int, int, int, int, str]:
        updated_first = 0 if (changed_ids is not None and ch.id in changed_ids) else 1
        return (updated_first, -ch.quality.rank, -ch.alev, -ch.awaken_lev, ch.id)

    return sorted(characters, key=key)
