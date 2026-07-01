from __future__ import annotations

from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.image.convert import convert_img

from ..utils.msgs import CatalogMsg, send_nte_notify
from ..utils.msgs.buttons import catalog_char_buttons
from ..utils.name_convert import alias_to_entity
from ..utils.resource.RESOURCE_PATH import CATALOG_CHAR_PATH, CATALOG_FORK_PATH

_ROSTER_PATHS: dict[str, Path] = {
    "角色": CATALOG_CHAR_PATH / "roster.webp",
    "武器": CATALOG_FORK_PATH / "roster.webp",
}


async def run_catalog(bot: Bot, ev: Event, query: str) -> None:
    hit = alias_to_entity(query)
    if hit is None:
        return await send_nte_notify(bot, ev, CatalogMsg.NOT_FOUND.format(name=query))

    reg, name, entity_id = hit

    paths = _catalog_paths(reg.kind, entity_id)
    existing = [p for p in paths if p.is_file()]
    if not existing:
        return await send_nte_notify(bot, ev, CatalogMsg.EMPTY.format(name=name))

    logger.info(f"[NTE图鉴] 发送 {reg.kind} {name} 图鉴 ({len(existing)} 张)")
    message = [MessageSegment.image(await convert_img(path)) for path in existing]
    if reg.kind == "char":
        await bot.send_option(message, catalog_char_buttons(name))
    else:
        await bot.send(message)


async def run_catalog_list(bot: Bot, ev: Event, kind: str) -> None:
    targets = _ROSTER_PATHS if kind == "图鉴" else {kind: _ROSTER_PATHS[kind]}
    existing = {label: path for label, path in targets.items() if path.is_file()}
    if not existing:
        return await send_nte_notify(bot, ev, CatalogMsg.LIST_EMPTY)

    logger.info(f"[NTE名册] 发送 {'+'.join(existing)} 名册 ({len(existing)} 张)")
    await bot.send([await convert_img(p) for p in existing.values()])


def _catalog_paths(kind: str, entity_id: str) -> list[Path]:
    if kind == "char":
        return [
            CATALOG_CHAR_PATH / f"{entity_id}_abilities.webp",
            CATALOG_CHAR_PATH / f"{entity_id}_awaken.webp",
        ]
    # 武器（弧盘）：当前一张就一张，文件名直接用 fork_id
    return [CATALOG_FORK_PATH / f"{entity_id}.webp"]
