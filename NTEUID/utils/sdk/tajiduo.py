from __future__ import annotations

import time
import random
import hashlib
from typing import Any, Dict, List, Optional

from .base import BaseSdkClient
from ..cache import timed_async_cache
from ..constants import (
    NOTICE_COLUMN_NAME,
    NOTICE_COMMUNITY_NAME,
    TAJIDUO_COMMUNITY_YIHUAN,
    SHARE_PLATFORM_WX_SESSION,
)
from .tajiduo_model import (
    _EMPTY_POST_AUTHOR,
    House,
    RoleHome,
    UserTasks,
    NoticePost,
    VehicleList,
    AreaProgress,
    GameRoleList,
    TajiduoError,
    GameSignState,
    NTENoticeType,
    PostShareData,
    GameRecordCard,
    GameSignReward,
    TajiduoRoleRef,
    TajiduoSession,
    CharacterDetail,
    SignRewardRecord,
    RecommendPostList,
    UserCoinTaskState,
    TeamRecommendation,
    AchievementProgress,
    CommunitySignResult,
    _parse,
    _PostAuthor,
    _expect_dict,
    _expect_dict_list,
    _GameRolesPayload,
)

TAJIDUO_BASE_URL = "https://bbs-api.tajiduo.com"
TAJIDUO_USER_CENTER_APP_ID = "10551"
TAJIDUO_COMMUNITY_APP = TAJIDUO_COMMUNITY_YIHUAN
TAJIDUO_APP_VERSION = "1.2.2"
TAJIDUO_CLIENT_UID = "0"
TAJIDUO_DS_SALT = "pUds3dfMkl"
TAJIDUO_DS_NONCE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789"
TAJIDUO_USER_AGENT = "okhttp/4.12.0"
TAJIDUO_WEB_USER_AGENT = "Mozilla/5.0"


class _TajiduoBase(BaseSdkClient):
    BASE_URL = TAJIDUO_BASE_URL
    error_cls = TajiduoError


class TajiduoClient(_TajiduoBase):
    USER_AGENT = TAJIDUO_USER_AGENT

    def __init__(
        self,
        device_id: str,
        *,
        access_token: str = "",
        refresh_token: str = "",
        center_uid: str = "",
        timeout: float = BaseSdkClient.timeout,
    ):
        if not device_id:
            raise ValueError("device_id 不能为空")
        self.device_id = device_id
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.center_uid = center_uid
        self.timeout = timeout

    @classmethod
    def from_user(cls, user: Any) -> "TajiduoClient":
        """业务层每次调 `from_user` 都会拿到一个只带 refresh_token 的 client；
        调用业务接口前必须先 `refresh_session()` 换出新的 access_token。"""
        return cls(
            device_id=user.dev_code,
            refresh_token=user.cookie,
            center_uid=user.center_uid,
        )

    def _default_headers(self) -> Dict[str, str]:
        return {
            "User-Agent": self.USER_AGENT,
            "platform": "android",
            "deviceid": self.device_id,
            "appversion": TAJIDUO_APP_VERSION,
            "uid": TAJIDUO_CLIENT_UID,
            "authorization": "",
        }

    def _finalize_headers(
        self,
        path: str,
        *,
        method: str,
        body: Optional[Dict[str, Any]],
        query: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Dict[str, str]:
        finalized = dict(headers)
        timestamp = str(int(time.time()))
        nonce = "".join(random.choice(TAJIDUO_DS_NONCE_ALPHABET) for _ in range(8))
        app_version = finalized.get("appversion", TAJIDUO_APP_VERSION)
        raw = f"{timestamp}{nonce}{app_version}{TAJIDUO_DS_SALT}"
        finalized["ds"] = f"{timestamp},{nonce},{hashlib.md5(raw.encode()).hexdigest()}"
        return finalized

    def _authed_headers(self) -> Dict[str, str]:
        if not self.access_token:
            raise self.error_cls("尚未登录塔吉多用户中心")
        headers = self._default_headers()
        headers["authorization"] = self.access_token
        return headers

    async def user_center_login(self, laohu_token: str, laohu_user_id: str) -> TajiduoSession:
        data = await self._request(
            "/usercenter/api/login",
            method="POST",
            body={
                "token": laohu_token,
                "userIdentity": str(laohu_user_id),
                "appId": TAJIDUO_USER_CENTER_APP_ID,
            },
        )
        access_token = data.get("accessToken")
        refresh_token = data.get("refreshToken")
        center_uid = data.get("uid")
        if access_token is None or refresh_token is None or center_uid is None:
            raise self.error_cls("塔吉多用户中心登录返回缺少 accessToken/refreshToken/uid", data)

        self.access_token = str(access_token)
        self.refresh_token = str(refresh_token)
        self.center_uid = str(center_uid)
        if not self.access_token or not self.refresh_token or not self.center_uid:
            raise self.error_cls("塔吉多用户中心登录返回 accessToken/refreshToken/uid 为空", data)
        return TajiduoSession(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            center_uid=self.center_uid,
            raw=data,
        )

    async def refresh_session(self) -> TajiduoSession:
        """用现有 refresh_token 换一组新的 accessToken + refreshToken。成功后 client 内部状态同步更新。"""
        if not self.refresh_token:
            raise self.error_cls("refresh_token 为空，无法续期")
        headers = self._default_headers()
        headers["authorization"] = self.refresh_token
        data = await self._request(
            "/usercenter/api/refreshToken",
            method="POST",
            headers=headers,
        )
        access_token = data.get("accessToken")
        new_refresh = data.get("refreshToken")
        if access_token is None or new_refresh is None:
            raise self.error_cls("塔吉多 refreshToken 未下发 accessToken/refreshToken", data)
        self.access_token = str(access_token)
        self.refresh_token = str(new_refresh)
        if not self.access_token or not self.refresh_token:
            raise self.error_cls("塔吉多 refreshToken 下发 accessToken/refreshToken 为空", data)
        return TajiduoSession(
            access_token=self.access_token,
            refresh_token=self.refresh_token,
            center_uid=self.center_uid,
            raw=data,
        )

    async def app_signin(self, community_id: str = TAJIDUO_COMMUNITY_APP) -> CommunitySignResult:
        data = await self._request(
            "/apihub/api/signin",
            method="POST",
            body={"communityId": community_id},
            headers=self._authed_headers(),
        )
        return _parse(CommunitySignResult, _expect_dict(data, "App 签到返回格式错误"), "App 签到返回格式错误")

    async def get_community_sign_state(self, community_id: str) -> bool:
        """`true` 表示当日该社区已签到；签到接口之前先调用避免重复扣接口配额。"""
        data = await self._request(
            "/apihub/api/getSignState",
            method="GET",
            query={"communityId": community_id},
            headers=self._authed_headers(),
        )
        if not isinstance(data, bool):
            raise self.error_cls("社区签到状态返回非布尔值", data if isinstance(data, dict) else {})
        return data

    async def get_bind_role(self, game_id: str) -> TajiduoRoleRef:
        """返回当前账号在 `game_id` 下的"主绑定"角色；无绑定时 `role_id=0`。"""
        data = await self._request(
            "/apihub/api/getGameBindRole",
            method="GET",
            query={"uid": self.center_uid, "gameId": game_id},
            headers=self._authed_headers(),
        )
        return _parse(TajiduoRoleRef, _expect_dict(data, "绑定角色返回格式错误"), "绑定角色返回格式错误")

    async def get_game_roles(self, game_id: str) -> GameRoleList:
        """列出当前账号在 `game_id` 下的全部角色（可能比 `get_bind_role` 多）。
        新版接口返回 `{bindRole, roles}`；老版本只给 list，两种都兼容。"""
        data = await self._request(
            "/usercenter/api/v2/getGameRoles",
            method="GET",
            query={"gameId": game_id},
            headers=self._authed_headers(),
        )
        if isinstance(data, list):
            raw_roles = _expect_dict_list(data, "角色列表格式错误")
            return GameRoleList(
                bind_role_id=0,
                roles=[_parse(TajiduoRoleRef, item, "角色列表格式错误") for item in raw_roles],
            )
        if isinstance(data, dict):
            parsed = _parse(_GameRolesPayload, data, "角色列表格式错误")
            return GameRoleList(bind_role_id=parsed.bind_role, roles=parsed.roles)
        raise self.error_cls("角色列表格式错误")

    async def bind_game_role(self, game_id: str, role_id: str) -> bool:
        """设该账号在 `game_id` 下的主绑定角色（触发 `bind_role` 成就任务 70 金币）。"""
        data = await self._request(
            "/usercenter/api/bindGameRole",
            method="POST",
            body={"gameId": game_id, "roleId": role_id},
            headers=self._authed_headers(),
        )
        if not isinstance(data, bool):
            raise self.error_cls("绑定角色返回非布尔值", data if isinstance(data, dict) else {})
        return data

    async def game_signin(self, role_id: str, game_id: str) -> dict:
        data = await self._request(
            "/apihub/awapi/sign",
            method="POST",
            body={"roleId": role_id, "gameId": game_id},
            headers=self._authed_headers(),
        )
        return _expect_dict(data, "游戏签到返回格式错误")

    async def get_game_sign_state(self, game_id: str) -> GameSignState:
        data = await self._request(
            "/apihub/awapi/signin/state",
            method="GET",
            query={"gameId": game_id},
            headers=self._authed_headers(),
        )
        return _parse(GameSignState, _expect_dict(data, "游戏签到状态格式错误"), "游戏签到状态格式错误")

    async def get_game_sign_rewards(self, game_id: str) -> List[GameSignReward]:
        data = await self._request(
            "/apihub/awapi/sign/rewards",
            method="GET",
            query={"gameId": game_id},
            headers=self._authed_headers(),
        )
        return _parse(GameSignReward, _expect_dict_list(data, "游戏签到奖励格式错误"), "游戏签到奖励格式错误")

    async def get_sign_reward_records(self, game_id: str) -> List[SignRewardRecord]:
        """已领取的游戏签到奖励历史（每条一件物品）。"""
        data = await self._request(
            "/apihub/awapi/sign/reward_records",
            method="GET",
            query={"gameId": game_id},
            headers=self._authed_headers(),
        )
        return _parse(
            SignRewardRecord,
            _expect_dict_list(data, "签到记录格式错误"),
            "签到记录格式错误",
        )

    async def get_game_record_card(self) -> List[GameRecordCard]:
        """当前账号名下所有游戏的战绩卡（roleName / serverName / lev 等）。"""
        data = await self._request(
            "/apihub/api/getGameRecordCard",
            method="GET",
            query={"uid": self.center_uid},
            headers=self._authed_headers(),
        )
        return _parse(
            GameRecordCard,
            _expect_dict_list(data, "战绩卡格式错误"),
            "战绩卡格式错误",
        )

    async def get_role_home(self, role_id: str) -> RoleHome:
        """异环角色综合面板：头像/等级/成就总览/区域总览/角色列表简版。"""
        data = await self._request(
            "/apihub/awapi/yh/roleHome",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        return _parse(RoleHome, _expect_dict(data, "角色面板格式错误"), "角色面板格式错误")

    async def get_role_characters_data(self, role_id: str) -> List[dict]:
        data = await self._request(
            "/apihub/awapi/yh/characters",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        return _expect_dict_list(data, "角色详情格式错误")

    async def get_role_characters(self, role_id: str) -> List[CharacterDetail]:
        """角色详细列表（每个角色 15+ 属性 + 城市技能 + 副手）。"""
        data = await self.get_role_characters_data(role_id)
        return _parse(
            CharacterDetail,
            data,
            "角色详情格式错误",
        )

    async def get_role_achievement_progress(self, role_id: str) -> AchievementProgress:
        data = await self._request(
            "/apihub/awapi/yh/achieveProgress",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        return _parse(
            AchievementProgress,
            _expect_dict(data, "成就进度格式错误"),
            "成就进度格式错误",
        )

    async def get_role_area_progress(self, role_id: str) -> List[AreaProgress]:
        data = await self._request(
            "/apihub/awapi/yh/areaProgress",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        return _parse(
            AreaProgress,
            _expect_dict_list(data, "区域进度格式错误"),
            "区域进度格式错误",
        )

    async def get_role_realestate(self, role_id: str) -> List[House]:
        data = await self._request(
            "/apihub/awapi/yh/realestate",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        wrapper = _expect_dict(data, "房产数据格式错误")
        return _parse(House, _expect_dict_list(wrapper.get("detail"), "房产数据格式错误"), "房产数据格式错误")

    async def get_role_vehicles(self, role_id: str) -> VehicleList:
        data = await self._request(
            "/apihub/awapi/yh/vehicles",
            method="GET",
            query={"roleId": role_id},
            headers=self._authed_headers(),
        )
        return _parse(VehicleList, _expect_dict(data, "载具数据格式错误"), "载具数据格式错误")

    async def get_user_tasks(self, gid: int = 1) -> UserTasks:
        """任务中心。`task_list1` = 每日任务（签到/浏览/点赞/分享），`task_list2` = 成就任务。"""
        data = await self._request(
            "/apihub/api/getUserTasks",
            method="GET",
            query={"gid": gid},
            headers=self._authed_headers(),
        )
        return _parse(UserTasks, _expect_dict(data, "任务列表格式错误"), "任务列表格式错误")

    async def get_user_coin_task_state(self) -> UserCoinTaskState:
        """金币任务今日进度（todayGet / todayTotal 等）。"""
        data = await self._request(
            "/apihub/api/getUserCoinTaskState",
            method="GET",
            headers=self._authed_headers(),
        )
        return _parse(UserCoinTaskState, _expect_dict(data, "金币任务状态格式错误"), "金币任务状态格式错误")

    async def list_recommend_posts(
        self,
        community_id: str,
        page: int = 1,
        count: int = 20,
        version: int = 0,
    ) -> RecommendPostList:
        """真实 APP 首请为 `page=1`（非 0）；业务层翻页时递增 `page`。"""
        data = await self._request(
            "/bbs/api/getRecommendPostList",
            method="GET",
            query={
                "communityId": community_id,
                "page": str(page),
                "count": str(count),
                "version": str(version),
            },
            headers=self._authed_headers(),
        )
        return _parse(RecommendPostList, _expect_dict(data, "推荐帖子列表格式错误"), "推荐帖子列表格式错误")

    async def like_post(self, post_id: str) -> bool:
        """data=true 表示本次点赞计入任务；data=false 表示已点过，本次未入账。"""
        data = await self._request(
            "/bbs/api/post/like",
            method="POST",
            body={"postId": post_id},
            headers=self._authed_headers(),
        )
        if not isinstance(data, bool):
            raise self.error_cls("点赞返回非布尔值", data if isinstance(data, dict) else {})
        return data

    async def view_post(self, post_id: str) -> dict:
        """浏览帖子（任务 `browse_post_c` 由此触发）；返回帖子详情 dict。"""
        data = await self._request(
            "/bbs/api/getPostFull",
            method="GET",
            query={"postId": post_id},
            headers=self._authed_headers(),
        )
        return _expect_dict(data, "浏览帖子返回格式错误")

    async def share_post(self, post_id: str, platform: str = SHARE_PLATFORM_WX_SESSION) -> None:
        """上报分享动作（用于任务 `share`）；成功时接口 data 为空，失败则 `_request` 会抛错。"""
        await self._request(
            "/bbs/api/post/share",
            method="POST",
            body={"postId": post_id, "platform": platform},
            headers=self._authed_headers(),
        )

    async def get_post_share_data(self, post_id: str) -> PostShareData:
        data = await self._request(
            "/bbs/api/post/getShareData",
            method="GET",
            query={"postId": post_id},
            headers=self._authed_headers(),
        )
        return _parse(PostShareData, _expect_dict(data, "分享数据格式错误"), "分享数据格式错误")


class TajiduoWebClient(_TajiduoBase):
    USER_AGENT = TAJIDUO_WEB_USER_AGENT

    @timed_async_cache(21600)
    async def get_team_recommendations(self) -> List[TeamRecommendation]:
        """异环配队推荐列表；APP 内嵌 `webstatic.tajiduo.com/bbs/team-rec/` 页面对应此接口。
        虽然路径在 `/awapi/`，但服务端不做鉴权，匿名调用即可。
        官方推荐变动很慢，缓存 6 小时。"""
        data = await self._request("/apihub/awapi/yh/team", method="GET")
        return _parse(
            TeamRecommendation,
            _expect_dict_list(data, "配队推荐格式错误"),
            "配队推荐格式错误",
        )

    @timed_async_cache(86400)
    async def get_notice_column_id(self) -> int:
        communities = _expect_dict_list(await self._request("/apihub/wapi/getAllCommunity"), "社区列表格式错误")
        for community in communities:
            if community.get("name") != NOTICE_COMMUNITY_NAME:
                continue
            for column in _expect_dict_list(community.get("columns"), "社区栏目格式错误"):
                if column.get("columnName") == NOTICE_COLUMN_NAME:
                    column_id = column.get("id")
                    if column_id is None:
                        raise TajiduoError("社区栏目 id 缺失", column)
                    return int(column_id)
        raise TajiduoError("未找到袋先生邮箱栏目")

    async def get_notice_list(
        self,
        notice_type: NTENoticeType,
        count: int = 10,
        version: int = 0,
    ) -> list[NoticePost]:
        data = _expect_dict(
            await self._request(
                "/bbs/wapi/getOfficialPostList",
                query={
                    "columnId": await self.get_notice_column_id(),
                    "count": count,
                    "version": version,
                    "officialType": int(notice_type),
                },
            ),
            "公告列表格式错误",
        )
        return self._merge_post_users(data.get("posts"), data.get("users"))

    async def get_notice_detail(self, post_id: int) -> NoticePost:
        data = _expect_dict(
            await self._request(
                "/bbs/wapi/getPostFull",
                query={"postId": post_id},
            ),
            "帖子详情格式错误",
        )
        post = data.get("post")
        if not isinstance(post, dict):
            raise TajiduoError("帖子详情不存在")
        return self._merge_post_users([post], data.get("users"))[0]

    @staticmethod
    def _merge_post_users(posts: Any, users: Any) -> list[NoticePost]:
        post_list = _expect_dict_list(posts, "帖子列表格式错误")
        raw_users = _expect_dict_list(users, "用户列表格式错误")
        authors = [_parse(_PostAuthor, u, "用户格式错误") for u in raw_users]
        user_map: Dict[Any, _PostAuthor] = {author.uid: author for author in authors}
        merged: list[NoticePost] = []
        for post in post_list:
            author = user_map.get(post.get("uid"), _EMPTY_POST_AUTHOR)
            enriched = {
                **post,
                "authorName": author.nickname,
                "authorAvatar": author.avatar,
            }
            merged.append(_parse(NoticePost, enriched, "帖子格式错误"))
        return merged


tajiduo_web = TajiduoWebClient()
