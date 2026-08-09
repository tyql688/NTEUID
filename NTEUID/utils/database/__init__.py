from __future__ import annotations

import json
from typing import Any, TypeVar, cast
from datetime import datetime

from sqlmodel import Field, col, select
from sqlalchemy import or_, and_, func, delete, tuple_, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from gsuid_core.webconsole.mount_app import PageSchema, GsAdminModel, site
from gsuid_core.utils.database.startup import exec_list
from gsuid_core.utils.database.base_models import User, BaseIDModel, with_session

from ..game_registry import PRIMARY_GAME_ID

exec_list.extend(
    [
        "ALTER TABLE NTEUser ADD COLUMN tap_id TEXT DEFAULT ''",
        "ALTER TABLE NTEUser ADD COLUMN xhh_pkey TEXT DEFAULT ''",
        "CREATE INDEX IF NOT EXISTS ix_nteuser_uid ON NTEUser (uid)",
        "CREATE INDEX IF NOT EXISTS ix_nteuser_user_id ON NTEUser (user_id)",
        # 评分榜走 char_id + score 排序，只回展示行；uid/grade 放进索引减少回表。
        "CREATE INDEX IF NOT EXISTS ix_ntechardata_char_id_score_uid ON ntechardata (char_id, score DESC, uid, grade)",
        # 排行展示按 (char_id, uid) 批量取 detail。
        "CREATE INDEX IF NOT EXISTS ix_ntechardata_char_id_uid ON ntechardata (char_id, uid)",
        # 群榜取本群参榜账号时同时过滤 bot_id，并按更新时间展示。
        "CREATE INDEX IF NOT EXISTS ix_ntegroupmember_group_bot_updated ON ntegroupmember (group_id, bot_id, updated_at DESC)",
        # 刷新面板登记群参榜账号时按 group_id + bot_id + uid 查旧行。
        "CREATE INDEX IF NOT EXISTS ix_ntegroupmember_group_bot_uid ON ntegroupmember (group_id, bot_id, uid)",
    ]
)

T_NTEUser = TypeVar("T_NTEUser", bound="NTEUser")
T_NTESignRecord = TypeVar("T_NTESignRecord", bound="NTESignRecord")
T_NTEGroupMember = TypeVar("T_NTEGroupMember", bound="NTEGroupMember")
T_NTECharData = TypeVar("T_NTECharData", bound="NTECharData")

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
    tap_id: str = Field(default="", title="TapTap user_id")
    xhh_pkey: str = Field(default="", title="小黑盒 user_pkey")
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
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
            )
            .order_by(col(cls.updated_at).desc())
            .limit(1)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def get_by_role(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        uid: str,
        game_id: str,
    ) -> T_NTEUser | None:
        result = await session.execute(
            select(cls)
            .where(
                cls.user_id == user_id,
                col(cls.uid) == uid,
                col(cls.game_id) == game_id,
                col(cls.access_token) != "",
                (col(cls.status).is_(None)) | (col(cls.status) == ""),
            )
            .order_by(col(cls.updated_at).desc())
            .limit(1)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def identity_by_uids(
        cls: type[T_NTEUser],
        session: AsyncSession,
        uids: list[str],
    ) -> dict[str, tuple[str, str]]:
        """按 uid 取身份 {uid: (user_id, role_name)}，给评分排名出榜 / 标红 / 头像用。
        同 uid 多行取 updated_at 最新一行。"""
        if not uids:
            return {}
        result = await session.execute(
            select(cls.uid, cls.user_id, cls.role_name)
            .where(col(cls.uid).in_(uids))
            .order_by(col(cls.updated_at).desc())
        )
        identity: dict[str, tuple[str, str]] = {}
        for uid, user_id, role_name in result.all():
            identity.setdefault(uid, (user_id, role_name))
        return identity

    @classmethod
    @with_session
    async def uids_of_user(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> set[str]:
        """某用户主游戏下全部角色 uid 集合（全服排名里定位"自己"用，小集合）。"""
        result = await session.execute(
            select(cls.uid).where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                col(cls.game_id) == PRIMARY_GAME_ID,
                col(cls.uid) != "",
            )
        )
        return set(result.scalars().all())

    @classmethod
    @with_session
    async def list_latest_per_account(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> list[T_NTEUser]:
        """按 center_uid 去重后每账号返回 updated_at 最新一行（忽略 status）。
        同 center_uid 多角色共享账号凭据，刷一次就够了，不用每个角色都跑一遍。
        不要拿来做单游戏业务查询——这个方法返回的行可能来自任意注册游戏。
        """
        result = await session.execute(
            select(cls)
            .where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
            )
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
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
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
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
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

        # 被移除的异环角色，连带清掉其评分快照 / 群参榜行，避免排名出现孤儿条目
        dropped_uids = [
            uid for (game_id, uid), _ in current.items() if (game_id, uid) not in keep and game_id == PRIMARY_GAME_ID
        ]
        if dropped_uids:
            await session.execute(delete(NTECharData).where(col(NTECharData.uid).in_(dropped_uids)))
            await session.execute(delete(NTEGroupMember).where(col(NTEGroupMember.uid).in_(dropped_uids)))

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
    async def upsert_access_token_account(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        center_uid: str,
        access_token: str,
        dev_code: str,
        entries: list[tuple[str, str, str]],
    ) -> None:
        """保存只有 center_uid + access_token 的低配登录态。

        access_token 不能续期，所以这里只更新可确定的账号字段，不清空旧的
        refreshToken / laohu 凭据；角色拉不到时保留或创建一条账号壳，避免后续查看、
        登出这类账号级操作把它当作完全未登录。
        """
        now = datetime.now()
        result = await session.execute(
            select(cls).where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.center_uid) == center_uid,
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            row.status = ""
            row.access_token = access_token
            row.access_token_updated_at = now
            row.dev_code = dev_code or row.dev_code
            row.updated_at = now

        current: dict[tuple[str, str], T_NTEUser] = {(row.game_id, row.uid): row for row in rows}
        if entries:
            for row in rows:
                if not row.uid:
                    await session.delete(row)
            for uid, role_name, game_id in entries:
                row = current.get((game_id, uid))
                if row is not None:
                    row.role_name = role_name
                    continue
                session.add(
                    cls(
                        user_id=user_id,
                        bot_id=bot_id,
                        center_uid=center_uid,
                        uid=uid,
                        role_name=role_name,
                        game_id=game_id,
                        status="",
                        dev_code=dev_code,
                        access_token=access_token,
                        access_token_updated_at=now,
                    )
                )
            return

        if not rows:
            session.add(
                cls(
                    user_id=user_id,
                    bot_id=bot_id,
                    center_uid=center_uid,
                    uid="",
                    role_name="",
                    game_id=PRIMARY_GAME_ID,
                    status="",
                    dev_code=dev_code,
                    access_token=access_token,
                    access_token_updated_at=now,
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
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
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
        *,
        exclude_game_ids: set[str] | None = None,
    ) -> dict[str, int]:
        """切换 (user_id, bot_id) 下"有效签到行"（uid/登录凭据非空、无 status）的 auto_sign。
        `exclude_game_ids` 命中的行**不动**（用于跳过被关闭签到的游戏）。返回每个被改动游戏的行数。
        """
        conds = [
            cls.user_id == user_id,
            cls.bot_id == bot_id,
            col(cls.uid) != "",
            (col(cls.cookie) != "") | (col(cls.access_token) != ""),
            (col(cls.status).is_(None)) | (col(cls.status) == ""),
        ]
        if exclude_game_ids:
            conds.append(~col(cls.game_id).in_(exclude_game_ids))

        count_result = await session.execute(select(cls.game_id, func.count()).where(*conds).group_by(cls.game_id))
        changed: dict[str, int] = {row[0]: row[1] for row in count_result.all()}
        if changed:
            await session.execute(update(cls).where(*conds).values(auto_sign="on" if on else "off"))
        return changed

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
    async def delete_by_center_uid(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        center_uid: str,
    ) -> int:
        """删除指定用户下某个 center_uid 的所有角色行（单账号登出）。"""
        result = cast(
            CursorResult,
            await session.execute(
                delete(cls).where(
                    col(cls.user_id) == user_id,
                    col(cls.bot_id) == bot_id,
                    col(cls.center_uid) == center_uid,
                ),
            ),
        )
        return result.rowcount

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
    async def has_logged_in_history(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
    ) -> bool:
        """是否曾经成功登录过任何塔吉多账号（登录凭据非空），不论当前是否被标失效。

        给 `not_logged_in` 文案分流用：True 表示业务层应建议先发【刷新令牌】尝试救活
        失效的登录态；False 表示从未登录，应直接发【登录】。
        """
        result = await session.execute(
            select(cls)
            .where(
                cls.user_id == user_id,
                cls.bot_id == bot_id,
                (col(cls.cookie) != "") | (col(cls.access_token) != ""),
            )
            .limit(1)
        )
        return result.scalars().first() is not None

    @classmethod
    @with_session
    async def set_tap_id(
        cls: type[T_NTEUser],
        session: AsyncSession,
        center_uid: str,
        tap_id: str,
    ) -> int:
        """给指定塔吉多账号下"异环角色行"写 tap_id。

        TapTap 战绩 API 按 app_id 区分（异环 = 714119），同账号下的幻塔角色行不
        共用这个 tap_id，所以只在 `game_id == PRIMARY_GAME_ID` 的行上写。
        """
        stmt = (
            update(cls)
            .where(
                col(cls.center_uid) == center_uid,
                col(cls.game_id) == PRIMARY_GAME_ID,
            )
            .values(tap_id=tap_id, updated_at=datetime.now())
        )
        return cast(CursorResult, await session.execute(stmt)).rowcount

    @classmethod
    @with_session
    async def set_xhh_bind(
        cls: type[T_NTEUser],
        session: AsyncSession,
        center_uid: str,
        pkey: str,
    ) -> int:
        """给指定塔吉多账号下"异环角色行"写小黑盒凭据。"""
        stmt = (
            update(cls)
            .where(
                col(cls.center_uid) == center_uid,
                col(cls.game_id) == PRIMARY_GAME_ID,
            )
            .values(xhh_pkey=pkey, updated_at=datetime.now())
        )
        return cast(CursorResult, await session.execute(stmt)).rowcount

    @classmethod
    @with_session
    async def mark_invalid_by_cookie(
        cls: type[T_NTEUser],
        session: AsyncSession,
        cookie: str,
        reason: str,
    ) -> None:
        await session.execute(update(cls).where(col(cls.cookie) == cookie).values(status=reason))

    @classmethod
    @with_session
    async def mark_invalid_by_account(
        cls: type[T_NTEUser],
        session: AsyncSession,
        user_id: str,
        bot_id: str,
        center_uid: str,
        reason: str,
    ) -> None:
        await session.execute(
            update(cls)
            .where(
                col(cls.user_id) == user_id,
                col(cls.bot_id) == bot_id,
                col(cls.center_uid) == center_uid,
            )
            .values(status=reason)
        )


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


class NTEGroupMember(BaseIDModel, table=True):
    """群 × 账号 的参榜登记，给「角色评分排名」按群圈定参榜号用。一行 = (group_id, bot_id, uid)。
    某账号在群里刷新面板时 upsert，多开多号→多行。`user_id` / `role_name` 是登记当时本群语境下的
    归属身份（钉死刷新者，不靠 NTEUser 全局反查——共享 / 转手账号时本群归属才准），群排名直接用、
    无需联表。全服(bot)排名没有群行，才退回 NTEUser 反查身份。登出按 uid 清。
    """

    __table_args__: dict[str, Any] = {"extend_existing": True}
    group_id: str = Field(default="", index=True, title="群组ID")
    bot_id: str = Field(default="", title="Bot ID")
    uid: str = Field(default="", index=True, title="角色roleId")
    user_id: str = Field(default="", title="本群归属用户ID")
    role_name: str = Field(default="", title="角色名")
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
        title="更新时间",
    )

    @classmethod
    @with_session
    async def upsert_member(
        cls: type[T_NTEGroupMember],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
        user_id: str,
        uid: str,
        role_name: str,
    ) -> None:
        """登记某账号在某群参榜（按 group_id+uid 唯一）；命中旧行刷新归属 + 时间，否则新插。"""
        now = datetime.now()
        result = await session.execute(
            select(cls).where(col(cls.group_id) == group_id, col(cls.bot_id) == bot_id, col(cls.uid) == uid)
        )
        row = result.scalars().first()
        if row is not None:
            row.user_id = user_id
            row.role_name = role_name
            row.updated_at = now
            return
        session.add(
            cls(group_id=group_id, bot_id=bot_id, uid=uid, user_id=user_id, role_name=role_name, updated_at=now)
        )

    @classmethod
    @with_session
    async def list_members(
        cls: type[T_NTEGroupMember],
        session: AsyncSession,
        group_id: str,
        bot_id: str,
    ) -> list[T_NTEGroupMember]:
        """某群全部参榜账号（updated_at 倒序）。"""
        result = await session.execute(
            select(cls)
            .where(col(cls.group_id) == group_id, col(cls.bot_id) == bot_id, col(cls.uid) != "")
            .order_by(col(cls.updated_at).desc())
        )
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def delete_by_uids(
        cls: type[T_NTEGroupMember],
        session: AsyncSession,
        bot_id: str,
        uids: list[str],
    ) -> int:
        """登出：把这些 uid 从所有群榜上清掉。"""
        if not uids:
            return 0
        result = cast(
            CursorResult,
            await session.execute(delete(cls).where(col(cls.bot_id) == bot_id, col(cls.uid).in_(uids))),
        )
        return result.rowcount


class NTECharData(BaseIDModel, table=True):
    """个人数据表，一行 = (uid, char_id)，取代旧的 playerinfo/{uid}.json 文件。
    只放与角色绑定的数据：`detail`（该角色完整 JSON，觉醒 / 套装 等出榜字段都在里面）、
    `score`（int 排序键走索引）和 `grade`（detail 里没有、我们算的；空 = 不可评分）。
    身份（user_id / role_name）不在这里，统一从 NTEUser 按 uid 现查——本群排名 / bot排名
    都这样取身份出榜 + 标红。排名只投影 (uid, score, grade) 按 score 倒序；展示的 ≤21 行
    再按 uid 取 detail 解析出觉醒 / 套装。
    """

    __table_args__: dict[str, Any] = {"extend_existing": True}
    uid: str = Field(default="", index=True, title="角色roleId")
    char_id: str = Field(default="", index=True, title="可玩角色charId")
    detail: str = Field(default="", title="该角色完整JSON")
    score: int = Field(default=0, title="评分")
    grade: str = Field(default="", title="评级(空=不可评分)")
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
        title="更新时间",
    )

    @classmethod
    @with_session
    async def replace_for_uid(
        cls: type[T_NTECharData],
        session: AsyncSession,
        uid: str,
        rows: list[dict[str, Any]],
    ) -> None:
        """刷新面板时整账号覆盖：先删该 uid 旧行，再按角色逐行插入（rows 只含 char_id/detail/score/grade）。"""
        await session.execute(delete(cls).where(col(cls.uid) == uid))
        for row in rows:
            session.add(cls(uid=uid, **row))

    @classmethod
    @with_session
    async def list_for_uid(cls: type[T_NTECharData], session: AsyncSession, uid: str) -> list[str]:
        """某账号全部角色的 detail JSON（面板/详情卡用）。"""
        result = await session.execute(select(cls.detail).where(col(cls.uid) == uid))
        return list(result.scalars().all())

    @classmethod
    @with_session
    async def has_for_uid(cls: type[T_NTECharData], session: AsyncSession, uid: str) -> bool:
        """判断某账号是否已有任何角色快照。"""
        result = await session.execute(select(cls.id).where(col(cls.uid) == uid).limit(1))
        return result.scalars().first() is not None

    @classmethod
    @with_session
    async def detail_for_uid_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        uid: str,
        char_id: str,
    ) -> str | None:
        """单角色详情用：按账号和角色直接取一条 detail JSON。"""
        result = await session.execute(
            select(cls.detail).where(col(cls.char_id) == char_id, col(cls.uid) == uid).limit(1)
        )
        return result.scalars().first()

    @classmethod
    @with_session
    async def rank_for_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        char_id: str,
        uids: list[str] | None = None,
        limit: int | None = None,
    ) -> list[tuple[str, int, str]]:
        """某角色可评分行按 score 倒序，投影 (uid, score, grade)。
        `uids` 给定 = 本群排名（按这批 uid 过滤）；为 None = bot排名（扫全表）。
        """
        stmt = (
            select(col(cls.uid), col(cls.score), col(cls.grade))
            .where(col(cls.char_id) == char_id, col(cls.grade) != "")
            .order_by(col(cls.score).desc(), col(cls.uid).asc())
        )
        if uids is not None:
            if not uids:
                return []
            stmt = stmt.where(col(cls.uid).in_(uids))
        if limit is not None:
            stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return [(uid, score, grade) for uid, score, grade in result.all()]

    @classmethod
    @with_session
    async def count_for_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        char_id: str,
        uids: list[str] | None = None,
    ) -> int:
        """某角色可评分账号数，给排行标题用，避免把全榜拉回 Python 后再 len。"""
        stmt = select(func.count()).select_from(cls).where(col(cls.char_id) == char_id, col(cls.grade) != "")
        if uids is not None:
            if not uids:
                return 0
            stmt = stmt.where(col(cls.uid).in_(uids))
        result = await session.execute(stmt)
        return int(result.scalar_one())

    @classmethod
    @with_session
    async def best_for_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        char_id: str,
        uids: list[str] | None = None,
    ) -> tuple[str, int, str] | None:
        """某角色最高分账号；最强面板只需要第一名，不能复用全榜查询。"""
        stmt = (
            select(col(cls.uid), col(cls.score), col(cls.grade))
            .where(col(cls.char_id) == char_id, col(cls.grade) != "")
            .order_by(col(cls.score).desc(), col(cls.uid).asc())
            .limit(1)
        )
        if uids is not None:
            if not uids:
                return None
            stmt = stmt.where(col(cls.uid).in_(uids))
        result = await session.execute(stmt)
        row = result.first()
        if row is None:
            return None
        uid, score, grade = row
        return uid, score, grade

    @classmethod
    @with_session
    async def rank_position_for_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        char_id: str,
        uid: str,
        score: int,
        uids: list[str] | None = None,
    ) -> int:
        """按 rank_for_char 的排序规则计算单行名次，用于只补一条掉榜自己的记录。"""
        stmt = (
            select(func.count())
            .select_from(cls)
            .where(
                col(cls.char_id) == char_id,
                col(cls.grade) != "",
                or_(col(cls.score) > score, and_(col(cls.score) == score, col(cls.uid) < uid)),
            )
        )
        if uids is not None:
            if not uids:
                return 1
            stmt = stmt.where(col(cls.uid).in_(uids))
        result = await session.execute(stmt)
        return int(result.scalar_one()) + 1

    @classmethod
    @with_session
    async def strongest_per_char(
        cls: type[T_NTECharData],
        session: AsyncSession,
        uids: list[str] | None = None,
    ) -> list[tuple[str, str, int, str]]:
        """每个角色评分最高的一行 (char_id, uid, score, grade)，按 score 降序——最强排行用。
        `uids` 给定 = 本群(按这批号过滤)；None = bot(全表)。
        DB 侧 `GROUP BY char_id` + `MAX(score)` 直接算完，只回每角色一行(~几十行)——
        不把全表(用户数×角色数)行 transfer 到 Python；SQLite bare column uid/grade 跟随 MAX 那行。
        """
        max_score = func.max(col(cls.score)).label("score")
        stmt = select(col(cls.char_id), col(cls.uid), max_score, col(cls.grade)).where(col(cls.grade) != "")
        if uids is not None:
            if not uids:
                return []
            stmt = stmt.where(col(cls.uid).in_(uids))
        stmt = stmt.group_by(col(cls.char_id))
        result = await session.execute(stmt)
        rows = [(char_id, uid, score, grade) for char_id, uid, score, grade in result.all()]
        return sorted(rows, key=lambda row: row[2], reverse=True)

    @classmethod
    @with_session
    async def details_for(
        cls: type[T_NTECharData],
        session: AsyncSession,
        uids: list[str],
        char_id: str,
    ) -> dict[str, str]:
        """出榜展示用：取这些 uid 该角色的 detail JSON，{uid: detail}。"""
        if not uids:
            return {}
        result = await session.execute(
            select(cls.uid, cls.detail).where(col(cls.char_id) == char_id, col(cls.uid).in_(uids))
        )
        return {uid: detail for uid, detail in result.all()}

    @classmethod
    @with_session
    async def details_for_pairs(
        cls: type[T_NTECharData],
        session: AsyncSession,
        pairs: list[tuple[str, str]],
    ) -> dict[tuple[str, str], str]:
        """按 (uid, char_id) 批量取 detail，给跨角色最强榜用。"""
        if not pairs:
            return {}
        result = await session.execute(
            select(cls.uid, cls.char_id, cls.detail).where(tuple_(col(cls.uid), col(cls.char_id)).in_(pairs))
        )
        return {(uid, char_id): detail for uid, char_id, detail in result.all()}

    @classmethod
    @with_session
    async def delete_by_uids(cls: type[T_NTECharData], session: AsyncSession, uids: list[str]) -> int:
        """登出时清掉这些账号的个人数据。"""
        if not uids:
            return 0
        result = cast(CursorResult, await session.execute(delete(cls).where(col(cls.uid).in_(uids))))
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


@site.register_admin
class NTEGroupMemberAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="异环群成员", icon="fa fa-user-friends")  # type: ignore
    model = NTEGroupMember


@site.register_admin
class NTECharDataAdmin(GsAdminModel):
    pk_name = "id"
    page_schema = PageSchema(label="异环个人数据", icon="fa fa-ranking-star")  # type: ignore
    model = NTECharData
