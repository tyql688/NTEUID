from __future__ import annotations

from enum import Enum, IntEnum
from typing import Any, List, Tuple, Optional
from dataclasses import dataclass

from pydantic import Field, BaseModel, ConfigDict, ValidationError

from .base import SdkError


class TajiduoError(SdkError):
    pass


class CharQuality(str, Enum):
    S = "ITEM_QUALITY_ORANGE"
    A = "ITEM_QUALITY_PURPLE"
    B = "ITEM_QUALITY_BLUE"
    C = "ITEM_QUALITY_GREEN"
    N = "ITEM_QUALITY_WHITE"

    @property
    def label(self) -> str:
        return self.name

    @property
    def letter(self) -> str:
        return self.name.lower()

    @property
    def rank(self) -> int:
        return {
            CharQuality.S: 4,
            CharQuality.A: 3,
            CharQuality.B: 2,
            CharQuality.C: 1,
            CharQuality.N: 0,
        }[self]


class CharElement(str, Enum):
    PSYCHE = "CHARACTER_ELEMENT_TYPE_PSYCHE"
    COSMOS = "CHARACTER_ELEMENT_TYPE_COSMOS"
    NATURE = "CHARACTER_ELEMENT_TYPE_NATURE"
    INCANTATION = "CHARACTER_ELEMENT_TYPE_INCANTATION"
    CHAOS = "CHARACTER_ELEMENT_TYPE_CHAOS"
    LAKSHANA = "CHARACTER_ELEMENT_TYPE_LAKSHANA"

    @property
    def label(self) -> str:
        return {
            CharElement.PSYCHE: "魂",
            CharElement.COSMOS: "光",
            CharElement.NATURE: "灵",
            CharElement.INCANTATION: "咒",
            CharElement.CHAOS: "暗",
            CharElement.LAKSHANA: "相",
        }[self]

    @property
    def color(self) -> Tuple[int, int, int]:
        return {
            CharElement.PSYCHE: (180, 110, 220),
            CharElement.COSMOS: (245, 190, 80),
            CharElement.NATURE: (95, 200, 150),
            CharElement.INCANTATION: (110, 145, 220),
            CharElement.CHAOS: (90, 90, 120),
            CharElement.LAKSHANA: (220, 110, 110),
        }[self]


class CharGroup(str, Enum):
    ONE = "CHARACTER_GROUP_TYPE_ONE"
    TWO = "CHARACTER_GROUP_TYPE_TWO"
    THREE = "CHARACTER_GROUP_TYPE_THREE"
    FOUR = "CHARACTER_GROUP_TYPE_FOUR"
    FIVE = "CHARACTER_GROUP_TYPE_FIVE"


@dataclass
class TajiduoSession:
    access_token: str
    refresh_token: str
    center_uid: str
    raw: dict


class _TajiduoModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class TajiduoRoleRef(_TajiduoModel):
    """`getGameBindRole` / `getGameRoles` 共用的角色引用；`role_id=0` 代表该位未绑定。"""

    role_id: int = Field(0, alias="roleId")
    role_name: str = Field("", alias="roleName")

    @property
    def uid(self) -> str:
        return str(self.role_id) if self.role_id else ""


class _GameRolesPayload(_TajiduoModel):
    bind_role: int = Field(
        0, alias="bindRole", description="主绑定角色 id；0 表示未设主绑定，需要触发 bind_role 日任务"
    )
    roles: List[TajiduoRoleRef] = Field(default_factory=list)


@dataclass(frozen=True)
class GameRoleList:
    """`bind_role_id=0` 代表账号在该游戏下未设主绑定角色——触发 `bind_role` 日任务的信号。"""

    bind_role_id: int
    roles: list[TajiduoRoleRef]


class CommunitySignResult(_TajiduoModel):
    exp: int = Field(0, description="社区签到获得的经验")
    gold_coin: int = Field(0, alias="goldCoin", description="社区签到获得的金币")


class TeamRecommendation(_TajiduoModel):
    id: str
    name: str
    icon: str = ""
    desc: str = ""
    imgs: List[str] = Field(default_factory=list)


class GameRecordRoleInfo(_TajiduoModel):
    account: str = ""
    game_id: int = Field(0, alias="gameId", description="游戏 ID（异环 / 幻塔 等）")
    gender: int = Field(-1, description="性别；-1 表示未填")
    lev: int = Field(0, description="角色等级")
    role_id: int = Field(0, alias="roleId")
    role_name: str = Field("", alias="roleName")
    server_id: int = Field(0, alias="serverId")
    server_name: str = Field("", alias="serverName")


class GameRecordCard(_TajiduoModel):
    game_id: int = Field(0, alias="gameId")
    game_name: str = Field("", alias="gameName")
    game_icon: str = Field("", alias="gameIcon")
    background_image: str = Field("", alias="backgroundImage")
    bind_role_info: Optional[GameRecordRoleInfo] = Field(None, alias="bindRoleInfo")
    link: str = ""


class SignRewardRecord(_TajiduoModel):
    create_time: int = Field(0, alias="createTime")
    icon: str = ""
    name: str = ""
    num: int = 0


class RoleHomeAchieveProgress(_TajiduoModel):
    achievement_cnt: int = Field(0, alias="achievementCnt", description="已达成成就数")
    total: int = Field(0, description="成就总数")


class RoleHomeAreaProgress(_TajiduoModel):
    id: str
    name: str
    progress: int = Field(0, description="该地区已探索数")
    total: int = Field(0, description="该地区可探索总数")


class RoleHomeRealEstate(_TajiduoModel):
    own_cnt: int = Field(0, alias="ownCnt", description="拥有房产数")
    show_id: str = Field("", alias="showId", description="当前展示房产 id（用于出图）")
    show_name: str = Field("", alias="showName")
    total: int = Field(0, description="可获得房产总数")


class RoleHomeVehicle(_TajiduoModel):
    own_cnt: int = Field(0, alias="ownCnt", description="拥有载具数")
    show_id: str = Field("", alias="showId", description="当前展示载具 id（用于出图）")
    show_name: str = Field("", alias="showName")
    total: int = Field(0, description="可获得载具总数")


class RoleHomeCharacter(_TajiduoModel):
    id: str
    name: str
    alev: int = Field(0, description="角色等级")
    slev: int = Field(0, description="混频等级")
    likeability_lev: int = Field(0, alias="likeabilitylev", description="好感度等级")
    awaken_lev: int = Field(0, alias="awakenLev", description="觉醒等级")
    awaken_effect: List[str] = Field(
        default_factory=list, alias="awakenEffect", description="已激活的觉醒效果列表（Effect1…Effect6）"
    )
    element_type: CharElement = Field(alias="elementType")
    group_type: CharGroup = Field(alias="groupType")
    quality: CharQuality


class RoleHome(_TajiduoModel):
    user_id: str = Field("", alias="userid")
    role_id: str = Field("", alias="roleid")
    role_name: str = Field("", alias="rolename")
    server_id: str = Field("", alias="serverid")
    server_name: str = Field("", alias="servername")
    avatar: str = Field("", description="当前展示头像 id（通常是角色 id）")
    lev: int = Field(0, description="角色等级")
    world_level: int = Field(0, alias="worldlevel")
    tycoon_level: int = Field(0, alias="tycoonLevel", description="大亨等级；决定都市活力上限")
    role_login_days: int = Field(0, alias="roleloginDays", description="角色累计活跃天数")
    charid_cnt: int = Field(0, alias="charidCnt", description="已获得角色数")
    stamina_value: int = Field(0, alias="staminaValue", description="本性像素当前值（体力）")
    stamina_max_value: int = Field(0, alias="staminaMaxValue", description="本性像素上限")
    city_stamina_value: int = Field(0, alias="citystaminaValue", description="都市活力当前值")
    city_stamina_max_value: int = Field(
        0, alias="citystaminaMaxValue", description="都市活力上限（受 tycoon_level 影响）"
    )
    day_value: int = Field(0, alias="dayvalue", description="今日活跃度（0–100）")
    week_copies_remain_cnt: int = Field(0, alias="weekcopiesremainCnt", description="周本剩余次数（封顶 3）")
    achieve_progress: Optional[RoleHomeAchieveProgress] = Field(None, alias="achieveProgress")
    area_progress: List[RoleHomeAreaProgress] = Field(default_factory=list, alias="areaProgress")
    realestate: Optional[RoleHomeRealEstate] = None
    vehicle: Optional[RoleHomeVehicle] = None
    characters: List[RoleHomeCharacter] = Field(default_factory=list)


class CharacterProperty(_TajiduoModel):
    """部分驱动盘 main_properties 项服务端只回 `{id}` 缺 `name`/`value`，
    pydantic 严格校验会让整张 CharacterDetail 失败；放宽成可选并默认空串，
    UI 侧已对空名/空值做过滤。"""

    id: str
    name: str = ""
    value: str = ""


class CharacterSkillItem(_TajiduoModel):
    title: str = ""
    desc: str = ""


class CharacterSkill(_TajiduoModel):
    id: str
    name: str = ""
    type: str = ""
    level: int = 0
    items: List[CharacterSkillItem] = Field(default_factory=list)


class CharacterFork(_TajiduoModel):
    """角色武器（弧盘）。`name` 是弧盘显示名（如 "预备备"），`buff_name` 是绑定 Buff 名（如 "「司令虎符」"）。
    `id` 形如 `fork_<拼音>`，走 `{CDN}/character/fork/<id>.png` 出图；未持有时 `id` 为空串。"""

    id: str = ""
    name: str = ""
    alev: str = "0"
    blev: str = "0"
    slev: str = "0"
    quality: Optional[CharQuality] = None
    group_type: Optional[CharGroup] = Field(None, alias="groupType")
    des: str = ""
    buff_name: str = Field("", alias="buffName")
    buff_des: str = Field("", alias="buffDes")
    lbd: List[str] = Field(default_factory=list)
    properties: List[CharacterProperty] = Field(default_factory=list)


class CharacterSuitItem(_TajiduoModel):
    id: str = ""
    name: str = ""
    lev: int = 0
    main_properties: List[CharacterProperty] = Field(default_factory=list, alias="mainProperties")
    properties: List[CharacterProperty] = Field(default_factory=list)


class CharacterSuit(_TajiduoModel):
    id: str = ""
    name: str = ""
    des2: str = ""
    des4: str = ""
    suit_condition: List[str] = Field(default_factory=list, alias="suitCondition")
    core: List[CharacterSuitItem] = Field(default_factory=list)
    pie: List[CharacterSuitItem] = Field(default_factory=list)
    suit_activate_num: int = Field(0, alias="suitActivateNum")


class CharacterDetail(_TajiduoModel):
    id: str
    name: str
    alev: int = Field(0, description="角色等级")
    slev: int = Field(0, description="混频等级")
    likeability_lev: int = Field(0, alias="likeabilitylev", description="好感度等级")
    awaken_lev: int = Field(0, alias="awakenLev", description="觉醒等级")
    awaken_effect: List[str] = Field(default_factory=list, alias="awakenEffect", description="已激活的觉醒效果列表")
    element_type: CharElement = Field(alias="elementType")
    group_type: CharGroup = Field(alias="groupType")
    quality: CharQuality
    properties: List[CharacterProperty] = Field(default_factory=list, description="角色属性面板项")
    skills: List[CharacterSkill] = Field(default_factory=list, description="战技列表")
    city_skills: List[CharacterSkill] = Field(default_factory=list, alias="citySkills", description="城区技能列表")
    fork: CharacterFork = Field(default_factory=lambda: CharacterFork(groupType=None, buffName="", buffDes=""))
    suit: CharacterSuit = Field(default_factory=lambda: CharacterSuit(suitActivateNum=0))


class AchievementCategory(_TajiduoModel):
    id: str
    name: str
    progress: int = 0
    total: int = 0


class AchievementProgress(_TajiduoModel):
    achievement_cnt: int = Field(0, alias="achievementCnt", description="已达成成就数")
    total: int = Field(0, description="成就总数")
    bronze_umd_cnt: int = Field(0, alias="bronzeUmdCnt", description="铜牌奖牌数")
    silver_umd_cnt: int = Field(0, alias="silverUmdCnt", description="银牌奖牌数")
    gold_umd_cnt: int = Field(0, alias="goldUmdCnt", description="金牌奖牌数")
    detail: List[AchievementCategory] = Field(default_factory=list)


class AreaDetailItem(_TajiduoModel):
    id: str
    name: str
    total: int = 0
    # 未开启/未解锁的子项服务端会给 null
    progress: Optional[int] = None


class AreaProgress(_TajiduoModel):
    id: str
    name: str
    progress: int = 0
    total: int = 0
    detail: List[AreaDetailItem] = Field(default_factory=list)


class Furniture(_TajiduoModel):
    id: str
    name: str
    own: bool = False


class House(_TajiduoModel):
    id: str
    name: str
    own: bool = False
    # 居住角色 id 列表的 JSON 字符串，如 "[1019]"；缺省房源没有
    chars: str = ""
    fdetail: List[Furniture] = Field(default_factory=list)


class VehicleBaseStat(_TajiduoModel):
    name: str
    # 接口里全部是字符串（"146"、"18000"），不做 int 转换
    value: str = ""


class VehicleAdvancedStat(VehicleBaseStat):
    max: str = ""


class VehicleModel(_TajiduoModel):
    """装饰 / 涂装子条目。`type` 才是 `{CDN}/verhicle/model/{type}.png` 的 id。"""

    id: str = ""
    type: str = ""


class Vehicle(_TajiduoModel):
    id: str
    name: str
    own: bool = False
    base: List[VehicleBaseStat] = Field(default_factory=list)
    advanced: List[VehicleAdvancedStat] = Field(default_factory=list)
    models: List[VehicleModel] = Field(default_factory=list)


class VehicleList(_TajiduoModel):
    detail: List[Vehicle] = Field(default_factory=list)
    own_cnt: int = Field(0, alias="ownCnt")
    show_id: str = Field("", alias="showId")
    show_name: str = Field("", alias="showName")
    total: int = 0


class GameSignState(_TajiduoModel):
    day: int = Field(description="今天是当月第几天")
    days: int = Field(description="本月已签到累计天数")
    month: int
    re_sign_cnt: int = Field(0, alias="reSignCnt", description="本月可补签次数")
    today_sign: bool = Field(False, alias="todaySign", description="今日是否已签")


class GameSignReward(_TajiduoModel):
    icon: str
    name: str
    num: int


class PostShareData(_TajiduoModel):
    title: str = ""
    content: str = ""
    image: str = ""


class NoticeImageRef(_TajiduoModel):
    url: str = ""


class NoticeVodRef(_TajiduoModel):
    cover: str = ""


class NoticePost(_TajiduoModel):
    post_id: int = Field(0, alias="postId")
    community_id: int = Field(0, alias="communityId")
    subject: str = ""
    create_time: int = Field(0, alias="createTime")
    author_name: str = Field("", alias="authorName")
    author_avatar: str = Field("", alias="authorAvatar")
    structured_content: str = Field("", alias="structuredContent")
    content: str = ""
    images: List[NoticeImageRef] = Field(default_factory=list)
    vods: List[NoticeVodRef] = Field(default_factory=list)


class _PostAuthor(_TajiduoModel):
    uid: int = 0
    nickname: str = ""
    avatar: str = ""


_EMPTY_POST_AUTHOR = _PostAuthor()


class RecommendPostList(_TajiduoModel):
    has_more: bool = Field(False, alias="hasMore")
    page: int = 0
    posts: List[NoticePost] = Field(default_factory=list)


class UserCoinTaskState(_TajiduoModel):
    today_get: int = Field(0, alias="todayGet", description="今日已获得金币")
    today_total: int = Field(0, alias="todayTotal", description="今日金币上限")
    total: int = Field(0, description="账户金币总数")


class UserTask(_TajiduoModel):
    task_key: str = Field(alias="taskKey")
    title: str
    coin: int = Field(0, description="完成一次的金币奖励")
    exp: int = Field(0, description="完成一次的经验奖励")
    complete_times: int = Field(0, alias="completeTimes", description="今日已完成次数")
    cont_times: int = Field(0, alias="contTimes", description="任务子计数（如浏览/点赞）")
    limit_times: int = Field(0, alias="limitTimes", description="今日封顶次数；到达后停止刷分")
    target_times: int = Field(1, alias="targetTimes", description="单次完成所需的子计数次数")
    period: int = 0
    uid: int = 0

    @property
    def finished(self) -> bool:
        """已达当日上限。`limit_times` 是每日封顶次数，completeTimes 到此即停。"""
        return self.limit_times > 0 and self.complete_times >= self.limit_times

    @property
    def remaining(self) -> int:
        return max(0, self.limit_times - self.complete_times)


class UserTasks(_TajiduoModel):
    daily: List[UserTask] = Field(default_factory=list, alias="task_list1")
    achievement: List[UserTask] = Field(default_factory=list, alias="task_list2")

    def find_daily(self, task_key: str) -> UserTask | None:
        for task in self.daily:
            if task.task_key == task_key:
                return task
        return None


class NTENoticeType(IntEnum):
    INFO = 1
    ACTIVITY = 2
    NOTICE = 3

    @property
    def label(self) -> str:
        return {
            NTENoticeType.INFO: "资讯",
            NTENoticeType.ACTIVITY: "活动",
            NTENoticeType.NOTICE: "公告",
        }[self]


def _parse(model: type[BaseModel], data: Any, message: str) -> Any:
    try:
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        return model.model_validate(data)
    except ValidationError as err:
        raise TajiduoError(f"{message}: {err}", data if isinstance(data, dict) else {}) from err


def _expect_dict(data: Any, message: str) -> dict:
    if not isinstance(data, dict):
        raise TajiduoError(message)
    return data


def _expect_dict_list(data: Any, message: str) -> list[dict]:
    if not isinstance(data, list):
        raise TajiduoError(message)
    result: list[dict] = []
    for item in data:
        if not isinstance(item, dict):
            raise TajiduoError(message)
        result.append(item)
    return result
