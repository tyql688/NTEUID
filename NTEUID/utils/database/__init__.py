from __future__ import annotations

import json
from typing import Any, TypeVar, cast
from datetime import datetime

from sqlmodel import Field, col, select
from sqlalchemy import delete, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.base_models import User, BaseIDModel, with_session

from ..game_registry import PRIMARY_GAME_ID

T_NTEUser = TypeVar("T_NTEUser", bound="NTEUser")
T_NTESignRecord = TypeVar("T_NTESignRecord", bound="NTESignRecord")

SIGN_KIND_APP = "app"
SIGN_KIND_GAME = "game"
SIGN_KIND_TASK_PREFIX = "task_"


def _today() -> str:
    return datetime.now().strftime("%Y-%m-%d")


class NTEUser(User, table=True):
    """一行 = 塔吉多账号(center_uid) × 游戏角色(uid) 的组合。

    同一个塔吉多账号有多个角色时存多行，`cookie` / `center_uid` / `dev_code`
    在同账号内是冗余相同的——签到时按 center_uid 分组，一次 refresh 复用于全部角色。
    """

    __table_args__: dict[str, Any] = {"extend_existing": True}
    cookie: str = Field(default="", title="refreshToken")
    uid: str = Field(default="", title="角色roleId")
    center_uid: str = Field(default="", title="塔吉多用户中心uid")
    role_name: str = Field(default="", title="角色名")
    game_id: str = Field(default="", title="游戏ID")
    dev_code: str = Field(default="", title="设备ID")
    laohu_token: str = Field(default="", title="laohuToken")
    laohu_user_id: str = Field(default="", title="laohu userId")
    auto_sign: str = Field(default="off", title="是否参与定时签到")
    access_token: str = Field(default="", title="accessToken 缓存")
    access_token_updated_at: datetime | None = Field(default=None, title="accessToken 更新时间")
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
        title="更新时间",
    )

    @classmethod
    @with_session
    async def get_active(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> T_NTEUser | None:
        """主游戏的一条真角色行（`uid != ""`）；没有就返回 None，业务层按"未登录"处理。"""
        result = await session.execute(
            select(cls)
            .where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                col(cls.game_id) == PRIMARY_GAME_ID,
                col(cls.uid) != "",
                col(cls.cookie) != "",
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
            )
            .order_by(col(cls.updated_at).desc())
            .limit(1)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def list_latest_per_account(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> list[T_NTEUser]:
        """【刷新令牌专用】按 center_uid 去重后每账号返回 updated_at 最新一行（忽略
        status）。同 center_uid 多角色共享 cookie/laohu_token，刷一次就够了，不用每个
        角色都跑一遍。不要拿来做业务查询——这个方法返回的行可能来自任意注册游戏。
        """
        result = await session.execute(
            select(cls)
            .where(cls.user_id == user_id, cls.bot_id == bot_id, col(cls.cookie) != "")
            .order_by(col(cls.updated_at).desc())
        )
        seen: set[str] = set()
        unique: list[T_NTEUser] = []
        for row in result.scalars().all():
            if row.center_uid not in seen:
                seen.add(row.center_uid)
                unique.append(row)
        return unique

    @classmethod
    @with_session
    async def list_sign_targets_by_user(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> list[T_NTEUser]:
        """【签到编排专用】列出该用户所有 (账号 × 游戏角色) 行，供签到 runner 按
        center_uid 分组跑完整签到。**会跨游戏**（异环 + 幻塔），不要用来做单游戏的
        业务查询；单用户单角色走 `get_active`。
        """
        result = await session.execute(
            select(cls)
            .where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                col(cls.uid) != "",
                col(cls.cookie) != "",
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
            )
            .order_by(col(cls.updated_at).desc())
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def list_sign_targets_all(
        cls: type[T_NTEUser],
        session: AsyncSession,
    ) -> list[T_NTEUser]:
        """【签到编排专用】全库 (账号 × 游戏角色) 行，供批量 / 定时签到跑全员。
        **会跨游戏**（异环 + 幻塔），不要用来做通用"列活跃用户"查询。
        """
        result = await session.execute(
            select(cls).where(
                col(cls.uid) != "",
                col(cls.cookie) != "",
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
            )
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def sync_account_roles(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        center_uid: str,
        entries: list[tuple[str, str, str]],
        **shared: Any,
    ) -> None:
        """一次性把某 center_uid 下的行对齐到 `entries = [(uid, role_name, game_id), ...]`：

        - entries 内的 (game_id, uid)：命中旧行就更新 role_name + shared；没命中就新插一行
        - entries 外的旧行：直接 delete

        全流程在同一个 session 里做，upsert + 清理天然原子；基类 `insert_data` 用
        (user_id, bot_id, uid) 判重，在多角色多行方案下会误判，所以这里直接走纯 ORM。
        """
        result = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.center_uid) == center_uid,
            )
        )
        current: dict[tuple[str, str], T_NTEUser] = {(row.game_id, row.uid): row for row in result.scalars().all()}
        keep = {(game_id, uid) for uid, _, game_id in entries}

        for key, row in current.items():
            if key not in keep:
                await session.delete(row)

        for uid, role_name, game_id in entries:
            row = current.get((game_id, uid))
            if row is not None:
                row.role_name = role_name
                for field_name, value in shared.items():
                    setattr(row, field_name, value)
            else:
                session.add(
                    cls(
                        user_id=user_id,
                        bot_id=bot_id,
                        center_uid=center_uid,
                        uid=uid,
                        role_name=role_name,
                        game_id=game_id,
                        **shared,
                    )
                )

    @classmethod
    @with_session
    async def update_tokens(
        cls: type[T_NTEUser],
        session: AsyncSession,
        center_uid: str,
        refresh_token: str,
        access_token: str,
    ) -> None:
        """refresh 成功后写回两种 token + 更新 access_token_updated_at + 清空 status。
        `access_token_updated_at` 用来算 TTL 决定下次要不要再 refresh。"""
        await session.execute(
            update(cls)
            .where(col(cls.center_uid) == center_uid)
            .values(
                cookie=refresh_token,
                access_token=access_token,
                access_token_updated_at=datetime.now(),
                status="",
            )
        )

    @classmethod
    @with_session
    async def list_sign_subscribers(
        cls: type[T_NTEUser],
        session: AsyncSession,
    ) -> list[T_NTEUser]:
        """【签到编排专用】全库 `auto_sign=on` 的行，定时签到"仅订阅模式"用。
        **会跨游戏**（异环 + 幻塔），不要用来做通用活跃订阅用户列表查询。
        """
        result = await session.execute(
            select(cls).where(
                col(cls.uid) != "",
                col(cls.cookie) != "",
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
                col(cls.auto_sign) == "on",
            )
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def set_auto_sign(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        on: bool,
    ) -> int:
        result = cast(
            CursorResult,
            await session.execute(
                update(cls)
                .where(col(cls.user_id) == user_id, col(cls.bot_id) == bot_id)
                .values(auto_sign="on" if on else "off")
            ),
        )
        return result.rowcount

    @classmethod
    @with_session
    async def touch_account(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        center_uid: str,
        when: datetime | None = None,
    ) -> int:
        """设 updated_at（默认当前）；显式 `.values(updated_at=...)` 不被 `onupdate` 覆盖，`get_active` 按 updated_at desc 选活跃账号。"""
        stmt = (
            update(cls)
            .where(col(cls.user_id) == user_id, col(cls.bot_id) == bot_id, col(cls.center_uid) == center_uid)
            .values(updated_at=datetime.now() if when is None else when)
        )
        return cast(CursorResult, await session.execute(stmt)).rowcount

    @classmethod
    @with_session
    async def delete_all(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> int:
        result = cast(
            CursorResult,
            await session.execute(
                delete(cls).where(col(cls.user_id) == user_id, col(cls.bot_id) == bot_id),
            ),
        )
        return result.rowcount

    @classmethod
    @with_session
    async def mark_invalid_by_cookie(
        cls: type[T_NTEUser],
        session: AsyncSession,
        cookie: str,
        reason: str,
    ) -> None:
        await session.execute(update(cls).where(col(cls.cookie) == cookie).values(status=reason))


class NTESignRecord(BaseIDModel, table=True):
    """签到明细 + 当日幂等。

    一次成功签到插入一行；存在即视为已签，避免重复调 API。`payload` 原样
    保留服务端返回的 JSON——关心"这次签了哪一项/拿到哪几样奖励"时读这里，
    不要在写入前把结构压平成几个数字字段。

    `ref_id` 对 App 签到是 `center_uid`，对游戏签到是 `gameId:roleId`；`kind`
    取 `SIGN_KIND_APP` / `SIGN_KIND_GAME`。社区子任务 `kind` 统一用
    `SIGN_KIND_TASK_PREFIX + task_key`（如 `task_like_post_c`），`ref_id` 仍是
    `center_uid`——落库后同日内整段短路，不再走远程 task 列表校验。
    """

    __table_args__: dict[str, Any] = {"extend_existing": True}
    ref_id: str = Field(title="center_uid(app) 或 gameId:roleId(game)")
    kind: str = Field(title="签到类型")
    date: str = Field(default_factory=_today, title="签到日期")
    payload: str = Field(default="", title="签到返回原文(JSON)")

    @classmethod
    @with_session
    async def is_signed(
        cls: type[T_NTESignRecord],
        session: AsyncSession,
        ref_id: str,
        kind: str,
        date: str | None = None,
    ) -> bool:
        day = _today() if date is None else date
        result = await session.execute(
            select(cls).where(
                col(cls.ref_id) == ref_id,
                col(cls.kind) == kind,
                col(cls.date) == day,
            )
        )
        return bool(result.scalars().first())

    @classmethod
    @with_session
    async def record(
        cls: type[T_NTESignRecord],
        session: AsyncSession,
        ref_id: str,
        kind: str,
        payload: dict | None = None,
        date: str | None = None,
    ) -> None:
        day = _today() if date is None else date
        raw_payload = {} if payload is None else payload
        exists = await session.execute(
            select(cls).where(
                col(cls.ref_id) == ref_id,
                col(cls.kind) == kind,
                col(cls.date) == day,
            )
        )
        if exists.scalars().first():
            return
        session.add(
            cls(
                ref_id=ref_id,
                kind=kind,
                date=day,
                payload=json.dumps(raw_payload, ensure_ascii=False),
            )
        )

    @classmethod
    @with_session
    async def purge_before(
        cls: type[T_NTESignRecord],
        session: AsyncSession,
        date: str,
    ) -> int:
        result = cast(
            CursorResult,
            await session.execute(delete(cls).where(col(cls.date) < date)),
        )
        return result.rowcount


@site.register_admin
class NTEUserAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="异环用户管理", icon="fa fa-users")  # type: ignore
    model = NTEUser


@site.register_admin
class NTESignRecordAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="异环签到记录", icon="fa fa-calendar-check")  # type: ignore
    model = NTESignRecord
