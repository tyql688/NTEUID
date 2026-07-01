import asyncio

from gsuid_core.logger import logger
from gsuid_core.server import on_core_start

from ..utils.sdk.base import set_proxy_provider
from ..nte_config.nte_config import NTEConfig
from ..utils.resource.git_resource import start_resources


@on_core_start(priority=-10)
async def sync_nte_ai_skills() -> None:
    from gsuid_core.ai_core.configs.ai_config import ai_config

    if not ai_config.get_config("enable").data:
        return

    from ..utils.ai_skills import sync_ai_skills

    await asyncio.to_thread(sync_ai_skills)


@on_core_start
async def all_start():
    set_proxy_provider(lambda: NTEConfig.get_config("NTEProxyUrl").data)
    await start_resources()
    logger.success("[NTEUID] 启动完成 ✅")
