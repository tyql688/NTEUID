from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .guide import get_guide
from ..utils.constants import COMMAND_NAME_PATTERN

sv_nte_guide = SV("nte攻略")


@sv_nte_guide.on_regex(rf"^(?P<char_name>{COMMAND_NAME_PATTERN})攻略$", block=True)
async def nte_guide_cmd(bot: Bot, ev: Event):
    await get_guide(bot, ev, ev.regex_dict["char_name"])
