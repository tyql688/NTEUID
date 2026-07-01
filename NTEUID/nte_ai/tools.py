from __future__ import annotations

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.ai_core.register import ai_tools

from ..utils.msgs import TITLE, LoginMsg, send_nte_notify
from ..utils.database import NTEUser, NTECharData, NTEGroupMember
from ..nte_guide.guide import get_guide
from ..utils.constants import GAME_ID_YIHUAN
from ..nte_help.get_help import get_help
from ..nte_notice.notice import render_notice_list, get_all_notice_list
from ..utils.msgs.buttons import sign_buttons
from ..utils.game_registry import PRIMARY_GAME_ID
from ..nte_sign.sign_runner import run_user_sign
from ..nte_code.code_service import run_code
from ..nte_role.rank_service import run_bot_rank, run_character_rank, run_strongest_board, run_strongest_panel
from ..nte_role.role_service import (
    run_explore,
    run_realtime,
    run_vehicles,
    run_role_home,
    run_realestate,
    run_achievement,
    run_character_level,
    run_character_detail,
    run_refresh_role_panel,
)
from ..nte_team.team_service import run_team
from ..nte_login.bind_service import view_bindings, switch_binding
from ..nte_notice.notice_card import draw_notice_list_img
from ..nte_sign.sign_calendar import run_sign_calendar
from ..nte_alias.alias_service import run_alias_list
from ..nte_gacha.gacha_service import run_my_gacha
from ..nte_login.login_service import request_login
from ..nte_catalog.catalog_service import run_catalog


async def _check_login(ev: Event) -> str | None:
    """检查用户登录状态。已登录返回 None；未登录或失效返回给 AI 的错误文本。"""
    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is not None:
        return None
    accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
    if accounts:
        return "用户登录已失效，请建议用户刷新令牌（nte_refresh）或重新登录（nte_login）。"
    return "用户尚未登录异环账号，请建议用户先登录（可调用 nte_login 工具发送登录链接）。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_account(bot: Bot, ev: Event) -> str:
    """查看异环账号主页、个人主页、资产概览。用户说"我的信息、uid、我的号、个人主页、账号"时调用；直接发送当前用户账号图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_role_home(bot, ev)
    return "已发送异环账号面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_character(bot: Bot, ev: Event, char_name: str) -> str:
    """查看异环单角色面板、装备、词条、评分、伤害。用户说"xx面板、xx装备、xx词条、看看xx练了没、帮我看看xx"时调用；疑似角色名+面板也用本工具。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。直接发图。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_character_detail(bot, ev, char_name)
    return "已发送异环角色面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_box(bot: Bot, ev: Event) -> str:
    """查看异环全角色练度、box 统计。仅在用户明确要"box、全角色练度、练度统计、该练谁、角色列表"时调用；不要用于某角色面板。直接发图。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_character_level(bot, ev)
    return "已发送异环全角色练度面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_stamina(bot: Bot, ev: Event) -> str:
    """查询异环体力、树脂、精力、本性像素、都市活力。用户说"查体力、异环体力、剩多少体力、体力满了没、看看我的体力"时调用；直接发送实时状态图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_realtime(bot, ev)
    return "已发送异环实时体力面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_refresh(bot: Bot, ev: Event) -> str:
    """刷新异环账号或角色面板缓存数据。用户说"刷新面板、重新获取、更新数据"时调用；刷新后直接发图。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_refresh_role_panel(bot, ev)
    return "已刷新异环面板数据并发送图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_explore(bot: Bot, ev: Event) -> str:
    """查看异环探索度、地图探索进度。用户说"探索度、地图探索、区域进度、探索率"时调用；直接发送当前用户探索图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_explore(bot, ev)
    return "已发送异环探索度面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_achievement(bot: Bot, ev: Event) -> str:
    """查看异环成就进度。用户说"成就、成就做了多少、成就列表、完成情况"时调用；直接发送当前用户成就图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_achievement(bot, ev)
    return "已发送异环成就面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_realestate(bot: Bot, ev: Event) -> str:
    """查看异环房产、房屋、住宅。用户说"房产、房屋、住宅、地产、家园"时调用；直接发送当前用户房产图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_realestate(bot, ev)
    return "已发送异环房产面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环面板", timeout=60.0)
async def nte_vehicle(bot: Bot, ev: Event) -> str:
    """查看异环载具、车辆。用户说"载具、车辆、车、摩托车、坐骑"时调用；直接发送当前用户载具图片面板。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_vehicles(bot, ev)
    return "已发送异环载具面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环资料", timeout=60.0)
async def nte_guide(bot: Bot, ev: Event, char_name: str) -> str:
    """查看异环角色攻略、养成图、配装推荐。用户说"xx攻略、怎么练、怎么养、培养建议、配装"时调用。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。直接发图。"""
    await get_guide(bot, ev, char_name)
    return "已发送异环角色攻略图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环资料", timeout=60.0)
async def nte_catalog(bot: Bot, ev: Event, name: str) -> str:
    """查看异环角色图鉴、武器图鉴。用户说"图鉴、角色图鉴、武器图鉴、百科、信息卡"时调用；name 填角色名、武器名或别名，后端会自动匹配。直接发图。"""
    await run_catalog(bot, ev, name)
    return "已发送异环图鉴图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环资料", timeout=60.0)
async def nte_team(bot: Bot, ev: Event, char_name: str) -> str:
    """查看异环角色配队推荐。用户说"配队、阵容、队伍推荐、组队、和谁组队"时调用。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。直接发图。"""
    await run_team(bot, ev, char_name)
    return "已发送异环配队推荐图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环资料", timeout=15.0)
async def nte_alias(bot: Bot, ev: Event, name: str) -> str:
    """查询异环角色或武器的别名列表。用户说"别名、有哪些名字、又叫什么"时调用；name 填角色名或武器名，返回该实体已注册的所有别名。"""
    await run_alias_list(bot, ev, name)
    return "已发送角色/武器别名列表。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环排行", timeout=60.0)
async def nte_group_rank(bot: Bot, ev: Event, char_name: str) -> str:
    """查看异环本群角色评分排行。用户说"本群排行、本群评分、群内谁最高"时调用。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。直接发图。"""
    await run_character_rank(bot, ev, char_name)
    return "已发送异环本群角色排行图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环排行", timeout=60.0)
async def nte_bot_rank(bot: Bot, ev: Event, char_name: str) -> str:
    """查看异环全 bot 角色评分排行。用户说"全 bot 排行、跨群排行、全服排行"时调用。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。直接发图。"""
    await run_bot_rank(bot, ev, char_name)
    return "已发送异环全 bot 角色排行图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环排行", timeout=60.0)
async def nte_strongest(bot: Bot, ev: Event, char_name: str, bot_scope: bool = False) -> str:
    """查看异环最强角色面板、最高评分账号。用户说"最强xx、最高评分、天花板面板"时调用。
    char_name 填用户原话中的角色名或疑似角色名，别名/谐音均可，后端会自动匹配。
    bot_scope=True 查全 bot，默认查本群。直接发图。"""
    await run_strongest_panel(bot, ev, char_name, bot_scope=bot_scope)
    return "已发送异环最强角色面板图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环排行", timeout=60.0)
async def nte_strongest_board(bot: Bot, ev: Event, bot_scope: bool = False) -> str:
    """查看异环各角色最强排行、战力榜。用户说"最强排行、各角色最高评分榜、战力榜"时调用；bot_scope=True 查全 bot，默认查本群。直接发图。"""
    await run_strongest_board(bot, ev, bot_scope=bot_scope)
    return "已发送异环最强排行榜图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环日常", timeout=60.0)
async def nte_sign(bot: Bot, ev: Event) -> str:
    """执行异环每日签到。用户说"签到、每日签到、打卡"时调用；执行当前用户异环签到并直接发送结果。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    result = await run_user_sign(ev.user_id, ev.bot_id)
    await bot.send_option(f"{TITLE}{result}", sign_buttons(), at_sender=bool(ev.group_id))
    return "已执行异环签到并发送结果。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环日常", timeout=60.0)
async def nte_sign_calendar(bot: Bot, ev: Event) -> str:
    """查看异环签到日历、签到奖励、月签进度。用户说"签到日历、签到奖励、月签进度"时调用；直接发送签到日历图片。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_sign_calendar(bot, ev, GAME_ID_YIHUAN)
    return "已发送异环签到日历图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环日常", timeout=30.0)
async def nte_notice(bot: Bot, ev: Event) -> str:
    """查看异环游戏公告。用户说"公告、最新公告、游戏通知、更新公告、活动公告"时调用；直接发送公告列表图片。"""
    columns = await get_all_notice_list()
    if not any(columns.values()):
        return "当前没有可用的异环公告内容。"
    await bot.send(await draw_notice_list_img(render_notice_list(columns)))
    return "已发送异环公告列表图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环日常", timeout=30.0)
async def nte_codes(bot: Bot, ev: Event) -> str:
    """查看异环兑换码、礼包码。用户说"兑换码、礼包码、cdk、code、激活码"时调用；直接发送当前可用兑换码。"""
    await run_code(bot, ev)
    return "已发送异环兑换码信息。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环抽卡", timeout=60.0)
async def nte_gacha(bot: Bot, ev: Event, query: str = "") -> str:
    """查看异环抽卡记录、抽卡统计。用户说"抽卡记录、出金记录、抽了多少、保底"时调用；
    query 可填 TapTap ID、小黑盒 pkey 或留空。直接发图。需要已登录。"""
    err = await _check_login(ev)
    if err:
        return err
    await run_my_gacha(bot, ev, query)
    return "已发送异环抽卡记录图片。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环账号", timeout=60.0)
async def nte_login(bot: Bot, ev: Event) -> str:
    """异环账号登录、绑定。用户说"登录、绑定账号、绑定异环、怎么登录、怎么绑号"时调用；发送登录链接引导用户完成绑定。"""
    await request_login(bot, ev)
    return "已发送异环登录链接，请引导用户打开链接完成登录。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环账号", timeout=30.0)
async def nte_bindings(bot: Bot, ev: Event) -> str:
    """查看异环账号绑定列表。用户说"查看绑定、绑了几个号、有哪些账号、我的账号"时调用；发送已绑定的账号列表。"""
    await view_bindings(bot, ev)
    return "已发送异环账号绑定列表。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环账号", timeout=30.0)
async def nte_switch(bot: Bot, ev: Event, target: str = "") -> str:
    """切换异环当前活跃账号。用户说"切换账号、换号、切号"时调用；target 填账号序号或 center_uid，留空则轮换到下一个账号。"""
    await switch_binding(bot, ev, target)
    return "已切换异环账号。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环账号", timeout=30.0)
async def nte_logout(bot: Bot, ev: Event, all_accounts: bool = False) -> str:
    """退出异环账号登录。用户说"退出登录、登出、解绑、注销"时调用；all_accounts=True 退出全部账号，默认只退出当前账号。"""
    if all_accounts:
        rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
        uids = [r.uid for r in rows if r.uid and r.game_id == PRIMARY_GAME_ID]
        deleted = await NTEUser.delete_all(ev.user_id, ev.bot_id)
        if not deleted:
            return "当前没有可退出的异环账号，用户可能尚未登录。"
        await NTECharData.delete_by_uids(uids)
        await NTEGroupMember.delete_by_uids(ev.bot_id, uids)
        logger.info(f"[NTE登出] AI 触发清理全部角色数据 uids={uids}")
        await send_nte_notify(bot, ev, LoginMsg.LOGOUT_ALL_DONE)
        return "已退出全部异环账号登录。"

    user = await NTEUser.get_active(ev.user_id, ev.bot_id)
    if user is None:
        accounts = await NTEUser.list_latest_per_account(ev.user_id, ev.bot_id)
        if not accounts:
            return "当前没有可退出的异环账号，用户可能尚未登录。"
        user = accounts[0]

    all_rows = await NTEUser.list_sign_targets_by_user(ev.user_id, ev.bot_id)
    uids = [r.uid for r in all_rows if r.uid and r.center_uid == user.center_uid and r.game_id == PRIMARY_GAME_ID]

    deleted = await NTEUser.delete_by_center_uid(ev.user_id, ev.bot_id, user.center_uid)
    if not deleted:
        return "退出登录失败，请稍后重试。"

    await NTECharData.delete_by_uids(uids)
    await NTEGroupMember.delete_by_uids(ev.bot_id, uids)
    logger.info(f"[NTE登出] AI 触发清理角色数据 uids={uids}")
    await send_nte_notify(bot, ev, LoginMsg.LOGOUT_DONE)
    return "已退出当前异环账号登录。"


@ai_tools(category="common", context_tags=["异环"], capability_domain="异环日常", timeout=15.0)
async def nte_help(bot: Bot, ev: Event) -> str:
    """查看异环功能帮助。用户说"帮助、怎么用、有什么功能、能做什么"时调用；发送功能帮助图片。"""
    from ..utils.msgs.buttons import help_buttons

    await bot.send_option(await get_help(ev.user_pm), help_buttons())
    return "已发送异环帮助图片。"
