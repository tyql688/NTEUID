from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .code_service import run_code

sv_nte_code = SV("nte兑换码")


@sv_nte_code.on_fullmatch(("兑换码", "code"))
async def nte_get_code(bot: Bot, ev: Event):
    await run_code(bot, ev)
