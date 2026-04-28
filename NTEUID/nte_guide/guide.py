from __future__ import annotations

import re
from typing import Any
from pathlib import Path

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.msgs import GuideMsg, send_nte_notify
from ..utils.name_convert import alias_to_char_name, char_name_to_char_id
from ..nte_config.nte_config import NTEConfig

GUIDE_PATH = Path(__file__).parent / "texture2d"


async def get_guide(bot: Bot, ev: Event, char_name: str) -> None:
    real_name = alias_to_char_name(char_name)
    if not real_name or not char_name_to_char_id(real_name):
        return await send_nte_notify(bot, ev, GuideMsg.CHAR_NOT_FOUND.format(char_name=char_name))

    logger.debug(f"[NTE攻略] 开始获取 {real_name} 图鉴")
    config = NTEConfig.get_config("NTEGuide").data
    authors = [p.name for p in GUIDE_PATH.iterdir() if p.is_dir()] if "all" in config else config

    pattern = re.compile(re.escape(real_name), re.IGNORECASE)
    imgs: list[Any] = []
    for author in authors:
        imgs += await _collect(GUIDE_PATH / author, pattern, author)

    if not imgs:
        return await send_nte_notify(bot, ev, GuideMsg.EMPTY.format(char_name=real_name))

    # 单作者单图时省掉「攻略作者：」文字头，直接发图。
    await bot.send(imgs[1] if "all" not in config and len(imgs) == 2 else imgs)


async def _collect(guide_dir: Path, pattern: re.Pattern, author: str) -> list[Any]:
    if not guide_dir.is_dir():
        logger.warning(f"[NTE攻略] 攻略目录不存在：{guide_dir}")
        return []
    imgs: list[Any] = []
    for file in guide_dir.iterdir():
        if not pattern.search(file.name):
            continue
        try:
            imgs.append(await convert_img(file))
        except Exception as exc:
            logger.warning(f"[NTE攻略] 图片读取失败 {file}: {exc}")
    if imgs:
        imgs.insert(0, f"攻略作者：{author}")
    return imgs
