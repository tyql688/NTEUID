from __future__ import annotations

from collections.abc import Iterable

from pydantic import ValidationError

from .gacha_model import (
    NTEGachaItem,
    NTEGachaSection,
    NTEGachaSummary,
    NTEGachaOverview,
)
from .archive_model import POOL_NAMES, PoolType, NTEGachaPool, NTEGachaRecord, NTEGachaArchive
from ..utils.name_convert import name_by_id
from ..utils.sdk.taptap_model import TaptapError, GachaSummary as TaptapGachaSummary
from ..utils.sdk.tajiduo_model import TajiduoError, TajiduoGachaPool
from ..utils.sdk.xiaoheihe_model import XiaoheiheError, LotteryAnalysis

_POOL_TYPES_BY_NAME: dict[str, PoolType] = {name: pool_type for pool_type, name in POOL_NAMES.items()}
_XHH_POOL_TYPES: dict[int, PoolType] = {1: "limited", 2: "permanent", 4: "weapon"}


def tap_to_archive(uid: str, summary: TaptapGachaSummary) -> NTEGachaArchive:
    normalized: dict[PoolType, NTEGachaPool] = {}
    try:
        for section in summary.sections:
            if section.banner_type not in _POOL_TYPES_BY_NAME:
                raise TaptapError(f"未识别的 TapTap 卡池：{section.banner_type}")
            pool_type = _POOL_TYPES_BY_NAME[section.banner_type]
            if pool_type in normalized:
                raise TaptapError(f"TapTap 返回重复卡池：{section.banner_type}")
            normalized[pool_type] = NTEGachaPool(
                records=[
                    NTEGachaRecord(
                        item_id=item.item_id,
                        time_ms=item.pull_time_ts * 1000,
                        time_precision="s",
                        pity=item.item_count,
                    )
                    for item in section.items
                ]
            )
        return NTEGachaArchive(
            format="nteuid-gacha",
            version=1,
            uid=uid,
            source="taptap",
            updated_at=summary.last_updated_ts,
            pools=normalized,
        )
    except ValidationError as error:
        raise TaptapError("TapTap 抽卡记录格式错误") from error


def xhh_to_archive(analysis: LotteryAnalysis) -> NTEGachaArchive:
    normalized: dict[PoolType, NTEGachaPool] = {}
    try:
        for pool in analysis.gacha_record:
            if pool.pool_key not in _XHH_POOL_TYPES:
                raise XiaoheiheError(f"未识别的小黑盒卡池：{pool.pool_key}")
            pool_type = _XHH_POOL_TYPES[pool.pool_key]
            if pool_type in normalized:
                raise XiaoheiheError(f"小黑盒返回重复卡池：{pool.pool_key}")
            normalized[pool_type] = NTEGachaPool(
                records=[
                    NTEGachaRecord(
                        item_id=record.item_id.lower().removesuffix("_256"),
                        time_ms=record.timestamp * 1000,
                        time_precision="s",
                        pity=record.diff,
                    )
                    for record in pool.records
                ]
            )
        return NTEGachaArchive(
            format="nteuid-gacha",
            version=1,
            uid=analysis.header_info.uid,
            source="xiaoheihe",
            updated_at=analysis.update_time,
            pools=normalized,
        )
    except ValidationError as error:
        raise XiaoheiheError("小黑盒抽卡记录格式错误") from error


def tjd_to_archive(uid: str, pools: Iterable[TajiduoGachaPool], updated_at: int) -> NTEGachaArchive:
    normalized: dict[PoolType, NTEGachaPool] = {}
    try:
        for pool in pools:
            if pool.tab not in _POOL_TYPES_BY_NAME:
                raise TajiduoError(f"未识别的官方卡池：{pool.tab}")
            normalized[_POOL_TYPES_BY_NAME[pool.tab]] = NTEGachaPool(
                records=[
                    NTEGachaRecord(item_id=detail.charid, time_ms=detail.timeStamp, pity=detail.rareCount)
                    for detail in pool.details
                ]
            )
        return NTEGachaArchive(
            format="nteuid-gacha",
            version=1,
            uid=uid,
            source="tajiduo",
            updated_at=updated_at,
            pools=normalized,
        )
    except ValidationError as error:
        raise TajiduoError("官方抽卡记录格式错误") from error


def archive_to_nte(archive: NTEGachaArchive) -> NTEGachaSummary:
    total_pull = sum(pool.draw_count for pool in archive.pools.values())
    total_ssr = sum(pool.s_count for pool in archive.pools.values())
    overview = NTEGachaOverview(total_pull_count=total_pull, total_ssr_count=total_ssr) if total_pull > 0 else None

    sections = [
        NTEGachaSection(
            banner_name=POOL_NAMES[pool_type],
            banner_type=POOL_NAMES[pool_type],
            total_pull_count=pool.draw_count,
            ssr_count=pool.s_count,
            avg_pity=int(pool.average),
            items=[
                NTEGachaItem(
                    item_id=record.item_id,
                    item_name=name_by_id(record.item_id),
                    pity=record.pity,
                    pull_time_ts=record.time_ms // 1000,
                )
                for record in pool.records
            ],
        )
        for pool_type, pool in archive.pools.items()
    ]

    return NTEGachaSummary(
        overview=overview,
        sections=sections,
        last_updated_ts=archive.updated_at,
    )
