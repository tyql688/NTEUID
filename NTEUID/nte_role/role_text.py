from __future__ import annotations

from typing import TYPE_CHECKING

from ..nte_config.prefix import NTE_PREFIX
from ..utils.sdk.tajiduo_model import CharQuality

if TYPE_CHECKING:
    from ..utils.sdk.tajiduo_model import CharacterDetail


def format_refresh_summary(characters: list["CharacterDetail"]) -> str:
    total = len(characters)
    lines = [f"已刷新 {total} 个角色"]
    if total:
        buckets: dict[CharQuality, list["CharacterDetail"]] = {}
        for character in characters:
            buckets.setdefault(character.quality, []).append(character)
        # 品质从高到低（S→A→B→C→N）逐组列名字
        for q in sorted(buckets, key=lambda x: x.rank, reverse=True):
            names = "、".join(c.name for c in buckets[q] if c.name)
            lines.append(f"{q.label}（{len(buckets[q])}）：{names}")
    lines.append(f"使用 `{NTE_PREFIX}<角色名>面板` 查看详情")
    return "\n".join(lines)
