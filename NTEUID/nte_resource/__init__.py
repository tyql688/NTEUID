from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.resource.git_resource import update_resources

sv_nte_resource = SV("nte资源", pm=1)


@sv_nte_resource.on_fullmatch(("下载全部资源"))
async def send_update_resource_msg(bot: Bot, ev: Event):
    await bot.send("[异环] 正在开始下载~可能需要较久的时间!")
    result = await update_resources(is_force=True)
    await bot.send(f"[异环] {result['message']}")
