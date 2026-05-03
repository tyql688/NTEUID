from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .gacha_help import draw_gacha_help
from .gacha_service import run_bind_tap, run_my_gacha

sv_nte_bind_tap = SV("nte绑定tap")
sv_nte_my_gacha = SV("nte抽卡记录")
sv_nte_gacha_help = SV("nte抽卡帮助")


@sv_nte_bind_tap.on_command(("绑定tap", "绑定TapTap", "绑定taptap", "绑定tap_id"), block=True)
async def nte_bind_tap_cmd(bot: Bot, ev: Event):
    await run_bind_tap(bot, ev, ev.text.strip())


@sv_nte_my_gacha.on_command(("抽卡记录", "我的抽卡"), block=True)
async def nte_my_gacha_cmd(bot: Bot, ev: Event):
    # 无参 → 走绑定 tap_id；带参 + NTEGachaUnsafeQuery 开 → 直查任意 tap_id
    await run_my_gacha(bot, ev, ev.text.strip())


@sv_nte_gacha_help.on_fullmatch(("抽卡帮助", "抽卡说明"), block=True)
async def nte_gacha_help_cmd(bot: Bot, ev: Event):
    await bot.send(await draw_gacha_help())
