from __future__ import annotations

from typing import TYPE_CHECKING

from ..nte_config.prefix import NTE_PREFIX
from ..utils.sdk.tajiduo_model import CharQuality

if TYPE_CHECKING:
    from ..utils.sdk.tajiduo_model import (
        House,
        RoleHome,
        VehicleList,
        CharacterDetail,
    )


_LIST_CAP = 10
_INDENT = "  "


def _cap_list(lines: list[str], total: int) -> list[str]:
    if total <= _LIST_CAP:
        return lines
    return [*lines[:_LIST_CAP], f"{_INDENT}...共 {total}"]


def format_role_home(home: "RoleHome") -> str:
    header = " · ".join(part for part in (home.role_name, home.server_name) if part)
    lines: list[str] = []
    if header:
        lines.append(header)
    lines.append(f"Lv{home.lev} · 世界 {home.world_level} · 大亨 {home.tycoon_level}")
    lines.append(f"登录 {home.role_login_days} 天 · 角色 {home.charid_cnt}")

    summary_parts: list[str] = []
    if home.achieve_progress is not None:
        summary_parts.append(f"成就 {home.achieve_progress.achievement_cnt}/{home.achieve_progress.total}")
    summary_parts.append(f"区域 {len(home.area_progress)}")
    if home.realestate is not None:
        summary_parts.append(f"房产 {home.realestate.total}")
    if home.vehicle is not None:
        summary_parts.append(f"载具 {home.vehicle.own_cnt}/{home.vehicle.total}")
    if summary_parts:
        lines.append(" · ".join(summary_parts))
    return "\n".join(lines)


def format_refresh_summary(characters: list["CharacterDetail"]) -> str:
    total = len(characters)
    lines = [f"已刷新 {total} 个角色"]
    if total:
        buckets: dict[CharQuality, list["CharacterDetail"]] = {}
        for character in characters:
            buckets.setdefault(character.quality, []).append(character)
        # 品质从高到低（S→A→B→C→N）逐组列名字
        for q in sorted(buckets, key=lambda x: x.rank, reverse=True):
            names = "、".join(c.name for c in buckets[q] if c.name)
            lines.append(f"{q.label}（{len(buckets[q])}）：{names}")
    lines.append(f"使用 `{NTE_PREFIX}<角色名>面板` 查看详情")
    return "\n".join(lines)


def format_realestate(houses: list["House"]) -> str:
    owned = sum(1 for house in houses if house.own)
    lines = [f"房产 · 已购 {owned}/{len(houses)}"]
    detail_lines: list[str] = []
    for house in houses:
        status = "已购" if house.own else "未购"
        furniture_total = len(house.fdetail)
        if furniture_total:
            furniture_own = sum(1 for item in house.fdetail if item.own)
            detail_lines.append(f"{_INDENT}{house.name} {status} · 家具 {furniture_own}/{furniture_total}")
        else:
            detail_lines.append(f"{_INDENT}{house.name} {status}")
    lines.extend(_cap_list(detail_lines, len(houses)))
    return "\n".join(lines)


def format_vehicles(vehicles: "VehicleList") -> str:
    lines = [f"载具 · 已购 {vehicles.own_cnt}/{vehicles.total}"]
    detail_lines = [f"{_INDENT}{vehicle.name} {'已购' if vehicle.own else '未购'}" for vehicle in vehicles.detail]
    lines.extend(_cap_list(detail_lines, len(vehicles.detail)))
    return "\n".join(lines)
