from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from .role_service import (
    run_explore,
    run_realtime,
    run_vehicles,
    run_role_home,
    run_realestate,
    run_achievement,
    run_character_detail,
    run_refresh_role_panel,
)
from ..utils.constants import COMMAND_NAME_PATTERN

sv_nte_role_home = SV("nte角色面板")
sv_nte_role_refresh = SV("nte刷新面板")
sv_nte_role_detail = SV("nte角色详情")
sv_nte_achievement = SV("nte成就进度")
sv_nte_realestate = SV("nte房产")
sv_nte_vehicle = SV("nte载具")
sv_nte_explore = SV("nte探索详情")
sv_nte_realtime = SV("nte实时信息")


@sv_nte_role_home.on_fullmatch(("查询", "卡片", "角色", "信息"), block=True)
async def nte_role_home(bot: Bot, ev: Event):
    await run_role_home(bot, ev)


@sv_nte_role_refresh.on_fullmatch(
    (
        "刷新面板",
        "刷新面版",
        "更新面板",
        "更新面版",
        "强制刷新",
        "面板刷新",
        "面板更新",
        "面板",
        "面版",
    ),
    block=True,
)
async def nte_role_refresh(bot: Bot, ev: Event):
    await run_refresh_role_panel(bot, ev)


@sv_nte_role_detail.on_regex(
    rf"^(?P<char_name>{COMMAND_NAME_PATTERN})(面板|信息|详情|面包|🍞)$",
    block=True,
)
async def nte_role_detail(bot: Bot, ev: Event):
    await run_character_detail(bot, ev, ev.regex_dict.get("char_name", ""))


@sv_nte_achievement.on_fullmatch(("成就进度", "成就"))
async def nte_achievement(bot: Bot, ev: Event):
    await run_achievement(bot, ev)


@sv_nte_realestate.on_fullmatch(("我的房产", "房产"))
async def nte_realestate(bot: Bot, ev: Event):
    await run_realestate(bot, ev)


@sv_nte_vehicle.on_fullmatch(("我的载具", "载具"))
async def nte_vehicle(bot: Bot, ev: Event):
    await run_vehicles(bot, ev)


@sv_nte_explore.on_fullmatch(("探索详情", "探索度", "探索"))
async def nte_explore(bot: Bot, ev: Event):
    await run_explore(bot, ev)


@sv_nte_realtime.on_fullmatch(("实时信息", "体力", "活力"))
async def nte_realtime(bot: Bot, ev: Event):
    await run_realtime(bot, ev)
