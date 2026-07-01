from __future__ import annotations

import random
import shutil
import asyncio
import hashlib
from io import BytesIO
from pathlib import Path

from PIL import Image
from cachetools import LRUCache

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment
from gsuid_core.utils.image.image_tools import change_ev_image_to_bytes

from ..utils.msgs import send_nte_notify
from ..utils.name_convert import CHARS
from ..nte_config.nte_config import NTEConfig
from ..utils.resource.RESOURCE_PATH import ROLE_PANEL_PATH

_IMAGE_SUFFIXES = frozenset(Image.registered_extensions())
_WEBP_QUALITY = 90
_ORIGINAL_IMAGE_CACHE: LRUCache[str, Path] = LRUCache(maxsize=256)


async def upload_character_panel_img(bot: Bot, ev: Event, char_name: str) -> None:
    if not ev.image_list:
        await send_nte_notify(bot, ev, "请随命令发送一张面板图")
        return

    resolved = _resolve_char(char_name)
    if resolved is None:
        await send_nte_notify(bot, ev, f"未找到角色：{char_name}")
        return
    real_name, char_id = resolved

    saved_count = 0
    failed_count = 0
    for image_source in ev.image_list:
        try:
            image_bytes = await change_ev_image_to_bytes(image_source)
            await asyncio.to_thread(save_character_panel_img, char_id, image_bytes)
            saved_count += 1
        except (OSError, ValueError):
            failed_count += 1

    if saved_count == 0:
        await send_nte_notify(bot, ev, "面板图保存失败")
        return

    msg = f"已上传{real_name}面板图{saved_count}张"
    if failed_count:
        msg += f"，失败{failed_count}张"
    await send_nte_notify(bot, ev, msg)


async def list_character_panel_imgs(bot: Bot, ev: Event, char_name: str) -> None:
    resolved = _resolve_char(char_name)
    if resolved is None:
        await send_nte_notify(bot, ev, f"未找到角色：{char_name}")
        return
    real_name, char_id = resolved

    panel_paths = await asyncio.to_thread(get_character_panel_paths, char_id)
    if not panel_paths:
        await send_nte_notify(bot, ev, f"暂无{real_name}面板图")
        return

    messages = [MessageSegment.text(f"{real_name}面板图列表：共{len(panel_paths)}张\n")]
    for image_path in panel_paths:
        messages.append(MessageSegment.text(f"\nID：{image_path.stem}\n"))
        messages.append(MessageSegment.image(image_path))
    await bot.send(messages)


async def delete_character_panel_img_by_id(bot: Bot, ev: Event, char_name: str, image_id: str) -> None:
    resolved = _resolve_char(char_name)
    if resolved is None:
        await send_nte_notify(bot, ev, f"未找到角色：{char_name}")
        return
    real_name, char_id = resolved

    image_path = await asyncio.to_thread(delete_character_panel_img, char_id, image_id)
    if image_path is None:
        await send_nte_notify(bot, ev, f"未找到{real_name}面板图：{image_id}")
        return

    await send_nte_notify(bot, ev, f"已删除{real_name}面板图：{image_path.stem}")


async def delete_all_character_panel_imgs(bot: Bot, ev: Event, char_name: str) -> None:
    resolved = _resolve_char(char_name)
    if resolved is None:
        await send_nte_notify(bot, ev, f"未找到角色：{char_name}")
        return
    real_name, char_id = resolved

    deleted_count = await asyncio.to_thread(delete_character_panel_dir, char_id)
    if deleted_count is None:
        await send_nte_notify(bot, ev, f"暂无{real_name}面板图")
        return

    await send_nte_notify(bot, ev, f"已删除{real_name}全部面板图：{deleted_count}张")


async def send_character_original_img(bot: Bot, ev: Event) -> None:
    if not NTEConfig.get_config("NTERoleOriginalImage").data:
        logger.info("[NTE角色原图] 角色原图功能已关闭")
        return

    if ev.reply is None:
        await send_nte_notify(bot, ev, "请引用角色面板图")
        return

    image_path = await asyncio.to_thread(get_original_image_path, ev.reply)
    if image_path is None:
        await send_nte_notify(bot, ev, "未找到对应原图")
        return

    await bot.send(MessageSegment.image(image_path))


async def delete_original_character_panel_img(bot: Bot, ev: Event) -> None:
    if ev.reply is None:
        await send_nte_notify(bot, ev, "请引用角色面板图")
        return

    image_path = await asyncio.to_thread(delete_original_image, ev.reply)
    if image_path is None:
        await send_nte_notify(bot, ev, "未找到对应原图")
        return

    await send_nte_notify(bot, ev, f"已删除原图：{image_path.name}")


async def compress_character_panel_imgs(bot: Bot, ev: Event) -> None:
    panel_paths = await asyncio.to_thread(get_all_character_panel_paths)
    if not panel_paths:
        await send_nte_notify(bot, ev, "暂无角色面板图")
        return

    results = await asyncio.gather(*(asyncio.to_thread(compress_character_panel_img, path) for path in panel_paths))
    compressed_count = sum(1 for compressed, _ in results if compressed)
    await send_nte_notify(
        bot,
        ev,
        f"面板图压缩完成：共{len(panel_paths)}张，压缩{compressed_count}张，跳过{len(panel_paths) - compressed_count}张",
    )


def get_character_panel_img(char_id: str | int) -> tuple[Path, Image.Image] | None:
    panel_paths = get_character_panel_paths(char_id)
    if not panel_paths:
        return None

    image_path = random.choice(panel_paths)
    with Image.open(image_path) as image:
        return image_path, image.convert("RGBA")


def cache_original_image(message_ids: list[str] | None, image_path: Path | None) -> None:
    if message_ids is None or image_path is None:
        return

    for message_id in message_ids:
        _ORIGINAL_IMAGE_CACHE[message_id] = image_path


def get_original_image_path(message_id: str | None) -> Path | None:
    if message_id is None:
        return None

    image_path = _ORIGINAL_IMAGE_CACHE.get(message_id)
    if image_path is not None and image_path.exists():
        return image_path

    return None


def delete_original_image(message_id: str | None) -> Path | None:
    if message_id is None:
        return None

    image_path = _ORIGINAL_IMAGE_CACHE.pop(message_id, None)
    if image_path is None:
        return None

    drop_original_image_cache(image_path)

    if not image_path.exists():
        return None

    image_path.unlink()
    _remove_empty_panel_dir(image_path.parent)
    return image_path


def drop_original_image_cache(image_path: Path) -> None:
    for message_id, cached_path in list(_ORIGINAL_IMAGE_CACHE.items()):
        if cached_path == image_path:
            _ORIGINAL_IMAGE_CACHE.pop(message_id, None)


def save_character_panel_img(char_id: str | int, image_bytes: bytes) -> None:
    panel_dir = _panel_dir(char_id)
    panel_dir.mkdir(parents=True, exist_ok=True)
    panel_path = panel_dir / f"{hashlib.sha1(image_bytes).hexdigest()[:16]}.webp"

    with Image.open(BytesIO(image_bytes)) as image:
        _save_webp(image.convert("RGBA"), panel_path)


def get_character_panel_paths(char_id: str | int) -> list[Path]:
    panel_dir = _panel_dir(char_id)
    if not panel_dir.is_dir():
        return []

    return sorted(path for path in panel_dir.iterdir() if path.is_file() and path.suffix.lower() in _IMAGE_SUFFIXES)


def get_all_character_panel_paths() -> list[Path]:
    if not ROLE_PANEL_PATH.is_dir():
        return []

    panel_paths: list[Path] = []
    for panel_dir in sorted(ROLE_PANEL_PATH.iterdir()):
        if panel_dir.is_dir():
            panel_paths.extend(get_character_panel_paths(panel_dir.name))
    return panel_paths


def compress_character_panel_img(image_path: Path) -> tuple[bool, Path]:
    if image_path.suffix.lower() == ".webp":
        return False, image_path

    output_path = image_path.with_suffix(".webp")
    if output_path.exists():
        return False, image_path

    tmp_path = output_path.with_name(f"{output_path.stem}.tmp.webp")
    original_size = image_path.stat().st_size

    with Image.open(image_path) as image:
        _save_webp(image.convert("RGBA"), tmp_path)

    compressed_size = tmp_path.stat().st_size
    if compressed_size >= original_size:
        tmp_path.unlink()
        return False, image_path

    tmp_path.replace(output_path)
    image_path.unlink()
    drop_original_image_cache(image_path)
    return True, output_path


def delete_character_panel_img(char_id: str | int, image_id: str) -> Path | None:
    for image_path in get_character_panel_paths(char_id):
        if image_path.stem != image_id and image_path.name != image_id:
            continue

        drop_original_image_cache(image_path)
        image_path.unlink()
        _remove_empty_panel_dir(image_path.parent)
        return image_path

    return None


def delete_character_panel_dir(char_id: str | int) -> int | None:
    panel_dir = _panel_dir(char_id)
    if not panel_dir.is_dir():
        return None

    panel_paths = get_character_panel_paths(char_id)
    for image_path in panel_paths:
        drop_original_image_cache(image_path)
    shutil.rmtree(panel_dir)
    return len(panel_paths)


def _resolve_char(char_name: str) -> tuple[str, str] | None:
    real_name = CHARS.name_of(char_name)
    if real_name is None:
        return None
    char_id = CHARS.id_of(real_name)
    if char_id is None:
        return None
    return real_name, char_id


def _panel_dir(char_id: str | int) -> Path:
    return ROLE_PANEL_PATH / str(char_id)


def _remove_empty_panel_dir(panel_dir: Path) -> None:
    if panel_dir.parent == ROLE_PANEL_PATH and not any(panel_dir.iterdir()):
        panel_dir.rmdir()


def _save_webp(image: Image.Image, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, "WEBP", quality=_WEBP_QUALITY, method=6)
