from __future__ import annotations

from pydantic import Field, BaseModel, ConfigDict


class _NteGachaModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class NTEGachaOverview(_NteGachaModel):
    total_pull_count: int = Field(description="总抽数（所有池子加起来）")
    total_ssr_count: int = Field(description="总 S 级命中次数")


class NTEGachaItem(_NteGachaModel):
    item_id: str = Field(description="物品 ID（角色用数字串、道具用字符串）")
    item_name: str = Field(description="物品名称")
    pity: int = Field(description="保底差值（距离上个 S 多少抽出的）")
    pull_time_ts: int = Field(description="抽中时间戳")


class NTEGachaSection(_NteGachaModel):
    banner_name: str = Field(description="池子展示名")
    banner_type: str = Field(default="", description="池子类型")
    banner_image: str = Field(default="", description="池子代表图 ID（角色 id 或道具 id）")
    begin_time_ts: int = Field(default=0, description="池子起始时间戳；0 表示来源未提供")
    end_time_ts: int = Field(default=0, description="池子结束时间戳；0 表示来源未提供")
    total_pull_count: int = Field(description="本池累计抽数")
    ssr_count: int = Field(description="本池 S 命中次数")
    avg_pity: int = Field(description="本池平均出 S 抽数")
    items: list[NTEGachaItem] = Field(default_factory=list, description="本池 S 卡明细")


class NTEGachaSummary(_NteGachaModel):
    overview: NTEGachaOverview | None = Field(
        default=None,
        description="总览。未抽过卡 / 未绑游戏角色时可能为空",
    )
    sections: list[NTEGachaSection] = Field(default_factory=list)
    last_updated_ts: int = Field(default=0, description="数据更新时间戳")

    @property
    def is_empty(self) -> bool:
        return self.overview is None or self.overview.total_pull_count == 0
