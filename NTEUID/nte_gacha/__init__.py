from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event
from gsuid_core.segment import MessageSegment

from .gacha_help import draw_gacha_help
from .tap_service import run_bind_tap
from .xhh_service import run_bind_xhh
from .gacha_service import run_my_gacha

sv_nte_bind_tap = SV("nte绑定tap")
sv_nte_bind_xhh = SV("nte绑定小黑盒")
sv_nte_my_gacha = SV("nte抽卡记录")
sv_nte_gacha_help = SV("nte抽卡帮助")


@sv_nte_bind_tap.on_command(("绑定tap", "绑定TapTap", "绑定taptap", "绑定tap_id"), block=True)
async def nte_bind_tap_cmd(bot: Bot, ev: Event):
    await run_bind_tap(bot, ev, ev.text)


@sv_nte_bind_xhh.on_command(("绑定小黑盒", "绑定xhh", "绑定heybox", "绑定小黑盒账号"), block=True)
async def nte_bind_xhh_cmd(bot: Bot, ev: Event):
    await run_bind_xhh(bot, ev, ev.text)


@sv_nte_my_gacha.on_command(("抽卡记录", "我的抽卡"), block=True)
async def nte_my_gacha_cmd(bot: Bot, ev: Event):
    # 无参 → 优先 TapTap，fallback 小黑盒；带参 + NTEGachaUnsafeQuery 开 → 免校验直查
    await run_my_gacha(bot, ev, ev.text)


@sv_nte_gacha_help.on_fullmatch(("抽卡帮助", "抽卡说明"), block=True)
async def nte_gacha_help_cmd(bot: Bot, ev: Event):
    await bot.send(MessageSegment.node(await draw_gacha_help()))
