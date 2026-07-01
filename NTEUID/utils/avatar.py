from __future__ import annotations

import httpx
from PIL import Image

from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.utils.image.image_tools import get_qq_avatar, get_event_avatar

from .cache import TimedCache
from .resource.cdn import get_avatar_img

_AVATAR_CACHE = TimedCache(timeout=3600.0, maxsize=512)


def _placeholder_avatar() -> Image.Image:
    return Image.new("RGBA", (640, 640), (170, 170, 170, 255))


async def _fallback_avatar(char_id: str | None) -> Image.Image:
    """QQ 头像抓不到时的兜底：优先该角色头像（get_avatar_img 命中本地即纯本地、不依赖网络），再退灰占位。"""
    if char_id:
        char_av = await get_avatar_img(char_id)
        if char_av is not None:
            return char_av
    return _placeholder_avatar()


async def fetch_avatar(ev: Event, user_id: str, char_id: str | None = None) -> Image.Image:
    """展示头像：按 user_id 缓存 1 小时；自己用事件头像，其他人取 QQ 头像。

    抓取失败（CDN 断连 / 解码失败）退兜底（角色头像 → 灰占位）且不缓存：既不让整张榜单渲染失败，又留给恢复后重试的机会。
    """
    hit = _AVATAR_CACHE.get(user_id)
    if hit is not None:
        return hit
    try:
        img = await get_event_avatar(ev) if user_id == ev.user_id else await get_qq_avatar(user_id)
    except (httpx.HTTPError, OSError) as exc:
        logger.warning(f"[NTE头像] 获取失败 user_id={user_id}: {exc}")
        return await _fallback_avatar(char_id)
    _AVATAR_CACHE.set(user_id, img)
    return img
