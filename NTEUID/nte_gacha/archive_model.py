from __future__ import annotations

from typing import Literal

from pydantic import Field, BaseModel, ConfigDict, model_validator

PoolType = Literal["limited", "permanent", "weapon"]
POOL_NAMES: dict[PoolType, str] = {
    "limited": "限定卡池",
    "permanent": "常驻卡池",
    "weapon": "弧盘池",
}


class _ArchiveModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class NTEGachaRecord(_ArchiveModel):
    item_id: str = Field(pattern=r"^(?:[0-9]+|fork_[a-z0-9_]+)$")
    time_ms: int = Field(gt=0)
    pity: int = Field(ge=1)
    time_precision: Literal["ms", "s"] = "ms"

    @model_validator(mode="after")
    def _validate_time_precision(self) -> NTEGachaRecord:
        if self.time_precision == "s" and self.time_ms % 1000:
            raise ValueError("秒精度记录的 time_ms 必须是 1000 的整数倍")
        return self

    @property
    def key(self) -> tuple[str, int, int]:
        return self.item_id, self.time_ms, self.pity

    @property
    def second_key(self) -> tuple[str, int, int]:
        return self.item_id, self.time_ms // 1000, self.pity


class NTEGachaPool(_ArchiveModel):
    records: list[NTEGachaRecord]

    @property
    def draw_count(self) -> int:
        return sum(record.pity for record in self.records)

    @property
    def s_count(self) -> int:
        return len(self.records)

    @property
    def average(self) -> float:
        return self.draw_count / self.s_count if self.s_count else 0.0


class NTEGachaArchive(_ArchiveModel):
    format: Literal["nteuid-gacha"]
    version: Literal[1]
    uid: str = Field(pattern=r"^[0-9]+$")
    source: Literal["tajiduo", "xiaoheihe", "taptap"]
    updated_at: int = Field(ge=0)
    pools: dict[PoolType, NTEGachaPool]

    @property
    def is_empty(self) -> bool:
        return all(not pool.records for pool in self.pools.values())
