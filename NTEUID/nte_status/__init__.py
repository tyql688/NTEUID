from datetime import datetime, timedelta

from PIL import Image
from sqlmodel import col, func, select

from gsuid_core.status.plugin_status import register_status
from gsuid_core.utils.database.base_models import async_maker

from ..utils.image import ICON
from ..utils.database import SIGN_KIND_GAME, NTEUser, NTESignRecord
from ..utils.constants import GAME_ID_YIHUAN


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


def _yesterday() -> str:
    return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")


async def _count_yihuan_accounts() -> int:
    """异环活跃账号数：与 `list_sign_targets_all` 同口径——绑了主游戏真角色、有 cookie、status 未失效。
    被 `mark_invalid_by_cookie` 标过期的不计入，与定时签到实际跑的账号集合保持一致。"""
    async with async_maker() as session:
        stmt = select(func.count(col(NTEUser.center_uid).distinct())).where(
            col(NTEUser.game_id) == GAME_ID_YIHUAN,
            col(NTEUser.uid) != "",
            col(NTEUser.cookie) != "",
            (col(NTEUser.status).is_(None)) | (col(NTEUser.status) == ""),
        )
        return int((await session.execute(stmt)).scalar_one())


async def _count_yihuan_signed_accounts(date: str) -> int:
    """`date` 当天有异环游戏签到记录的账号数（按 `center_uid` 去重）。
    `NTESignRecord.ref_id` 形如 `1289:{roleId}`，先收集 roleId 再反查 `NTEUser.center_uid`。"""
    prefix = f"{GAME_ID_YIHUAN}:"
    async with async_maker() as session:
        ref_rows = await session.execute(
            select(col(NTESignRecord.ref_id)).where(
                col(NTESignRecord.kind) == SIGN_KIND_GAME,
                col(NTESignRecord.ref_id).startswith(prefix),
                col(NTESignRecord.date) == date,
            )
        )
        role_ids = {r.split(":", 1)[1] for r in ref_rows.scalars().all()}
        if not role_ids:
            return 0
        stmt = select(func.count(col(NTEUser.center_uid).distinct())).where(
            col(NTEUser.game_id) == GAME_ID_YIHUAN,
            col(NTEUser.uid).in_(role_ids),
        )
        return int((await session.execute(stmt)).scalar_one())


async def get_account_num() -> int:
    return await _count_yihuan_accounts()


async def get_today_sign_num() -> int:
    return await _count_yihuan_signed_accounts(_today())


async def get_yesterday_sign_num() -> int:
    return await _count_yihuan_signed_accounts(_yesterday())


register_status(
    Image.open(ICON).convert("RGBA"),
    "NTEUID",
    {
        "异环账号": get_account_num,
        "今日签到": get_today_sign_num,
        "昨日签到": get_yesterday_sign_num,
    },
)
