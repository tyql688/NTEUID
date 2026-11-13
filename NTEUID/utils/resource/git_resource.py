from zlib import error as ZlibError
from zipfile import BadZipFile

import httpx

from gsuid_core.pool import to_thread
from gsuid_core.logger import logger

from ..restart import update_lock, restart_after_update
from .release_files import RECEIPT
from .RESOURCE_PATH import STATIC_RESOURCE_PATH
from .scratch_items import load_scratch_items
from .release_update import ResourceUpdateResult, sync_release
from .suit_properties import load_suit_properties


async def update_resources(is_force: bool = False, silent: bool = False) -> ResourceUpdateResult:
    async with update_lock:
        try:
            result = await to_thread(sync_release)(STATIC_RESOURCE_PATH, force=is_force)
            if result["changed"]:
                from ..name_convert import reload_all

                await to_thread(reload_all)()
                await load_scratch_items(force=True)
                await load_suit_properties()
        except (httpx.HTTPError, OSError, ValueError, KeyError, EOFError, BadZipFile, ZlibError) as error:
            logger.warning(f"[NTEUID] 资源同步失败 {type(error).__name__}")
            logger.debug(f"[NTEUID] {error}")
            return {"success": False, "message": "资源暂未同步，请稍后重试", "files_changed": 0, "changed": False}
        if result["changed"] or not silent:
            logger.info(f"[NTEUID] {result['message']}")
        return result


async def init_resources() -> None:
    result = await update_resources()
    if result["changed"]:
        await restart_after_update()
    else:
        await load_scratch_items()
        await load_suit_properties()


async def start_resources() -> None:
    if (STATIC_RESOURCE_PATH / ".git").exists() or (STATIC_RESOURCE_PATH / RECEIPT).is_file():
        from ..background import create_background_task

        create_background_task(init_resources())
    else:
        await init_resources()
