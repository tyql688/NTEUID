from gsuid_core.sv import SV
from gsuid_core.bot import Bot
from gsuid_core.models import Event

from . import login_router, query_router
from .scratch_service import (
    run_scratch_rank,
    run_scratch_query,
    send_scratch_login,
    bind_scratch_cookie,
    unbind_scratch_cookie,
)

_ = (login_router, query_router)  # 纯副作用 import：FastAPI 路由在模块加载时注册

# 固定命令：
#   nte刮刮乐排行 → 群内亏损排行（高优先级，避免被角色评分排名正则拦截）
#   nte刮刮乐登录 → 登录/重绑完美世界账号
#   nte刮刮乐     → 查询（首次未绑定会自动引导登录）

sv_nte_scratch_rank = SV("nte刮刮乐排行", priority=4)


@sv_nte_scratch_rank.on_command("刮刮乐排行", block=True)
async def nte_scratch_rank_cmd(bot: Bot, ev: Event):
    await run_scratch_rank(bot, ev)


sv_nte_scratch_login = SV("nte刮刮乐登录")


@sv_nte_scratch_login.on_command("刮刮乐登录", block=True)
async def nte_scratch_login_cmd(bot: Bot, ev: Event):
    await send_scratch_login(bot, ev)


sv_nte_scratch = SV("nte刮刮乐")


@sv_nte_scratch.on_command("刮刮乐", block=True)
async def nte_scratch(bot: Bot, ev: Event):
    text = ev.text.strip()
    # 手动绑定/解绑作为兜底入口（正常用户用不到）
    if text.startswith("绑定"):
        ev.text = text[len("绑定") :].strip()
        return await bind_scratch_cookie(bot, ev)
    if text.startswith("解绑"):
        return await unbind_scratch_cookie(bot, ev)
    await run_scratch_query(bot, ev, text)
