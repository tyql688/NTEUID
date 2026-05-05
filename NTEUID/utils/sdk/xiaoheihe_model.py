from __future__ import annotations

from typing import Any

from pydantic import Field, BaseModel, ConfigDict, ValidationError, field_validator

from .base import SdkError


class XiaoheiheError(SdkError):
    """小黑盒接口失败的基类。"""


class _XiaoheiheModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class HeaderInfo(_XiaoheiheModel):
    name: str = Field(default="", description="玩家昵称")
    avatar: str = Field(default="", description="头像 URL")
    server: str = Field(default="", description="服务器名")
    level: str = Field(default="", description="玩家等级")
    uid: str = Field(default="", description="游戏内 UID")


class PoolStat(_XiaoheiheModel):
    pool: str = Field(description="池子名称")
    cost: int = Field(description="本池累计抽数")
    ssr: int = Field(description="本池 S 命中次数")


class StatisticInfo(_XiaoheiheModel):
    total_limit_cost: int = Field(default=0, description="限定池总抽数")
    total_fork_cost: int = Field(default=0, description="弧盘池总抽数")
    total_permanent_cost: int = Field(default=0, description="常驻池总抽数")
    temp_title: str = Field(default="", description="欧气评级称号")
    count_time: int = Field(default=0, description="统计截止时间戳")
    is_lucky: bool = Field(default=False, description="是否欧皇")
    pool_stats: list[PoolStat] = Field(default_factory=list)


class GachaRecordItem(_XiaoheiheModel):
    name: str = Field(description="物品名称")
    img: str = Field(description="物品图标 URL")
    timestamp: int = Field(description="抽中 unix 秒")
    diff: int = Field(description="距离上个 S 的抽数（保底差值）")


class GachaPoolRecord(_XiaoheiheModel):
    pool_type: str = Field(description="池子名称")
    pool_key: int = Field(description="池子标识")
    records: list[GachaRecordItem] = Field(default_factory=list)


class UserSettings(_XiaoheiheModel):
    hide_user_info: bool = Field(default=False)


class LotteryAnalysis(_XiaoheiheModel):
    is_bind: bool = Field(default=False, description="是否已绑定异环角色")
    update_time: int = Field(default=0, description="数据更新时间戳")
    could_refresh: bool = Field(default=False, description="是否可刷新数据")
    header_info: HeaderInfo = Field(default_factory=HeaderInfo)
    statistic_info: StatisticInfo = Field(default_factory=StatisticInfo)
    gacha_record: list[GachaPoolRecord] = Field(default_factory=list)
    user_settings: UserSettings = Field(default_factory=UserSettings)

    @field_validator("header_info", mode="before")
    @classmethod
    def _default_header_info(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("statistic_info", mode="before")
    @classmethod
    def _default_statistic_info(cls, value: Any) -> Any:
        return {} if value is None else value

    @field_validator("user_settings", mode="before")
    @classmethod
    def _default_user_settings(cls, value: Any) -> Any:
        return {} if value is None else value

    @property
    def is_empty(self) -> bool:
        return (
            self.statistic_info.total_limit_cost == 0
            and self.statistic_info.total_permanent_cost == 0
            and self.statistic_info.total_fork_cost == 0
        )


def _parse(model: type[BaseModel], data: Any, message: str) -> Any:
    try:
        if isinstance(data, list):
            return [model.model_validate(item) for item in data]
        return model.model_validate(data)
    except ValidationError as err:
        raise XiaoheiheError(f"{message}: {err}", data if isinstance(data, dict) else {}) from err


def _expect_dict(data: Any, message: str) -> dict[str, Any]:
    if not isinstance(data, dict):
        raise XiaoheiheError(message)
    return data
