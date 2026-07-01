from __future__ import annotations

import json
from typing import Any
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import httpx

from gsuid_core.ai_core.register import ai_tools

from ..utils.name_convert import CHARS


async def _graphql(query: str, variables: dict[str, object] | None = None) -> dict[str, Any]:
    payload: dict[str, object] = {"query": query}
    if variables is not None:
        payload["variables"] = variables
    async with httpx.AsyncClient(timeout=20, follow_redirects=True) as client:
        resp = await client.post(
            "https://everness.info/api/graphql",
            json=payload,
            cookies={"locale": "zh-Hans"},
            headers={
                "origin": "https://everness.info",
                "referer": "https://everness.info/zh-Hans",
                "accept-language": "zh-CN,zh-Hans;q=0.9,zh;q=0.8,en;q=0.5",
            },
        )
    resp.raise_for_status()
    body = resp.json()
    if not isinstance(body, dict):
        return {}
    errors = body.get("errors")
    if isinstance(errors, list) and errors:
        return {"errors": errors}
    data = body.get("data")
    if isinstance(data, dict):
        return data
    return {}


def _pick(items: list[dict[str, Any]], query: str) -> dict[str, Any] | None:
    q = query.casefold().strip()
    for item in items:
        targets: list[str] = []
        for key in ("id", "name"):
            value = item.get(key)
            if value is not None:
                targets.append(str(value).strip().casefold())
        if q and q in targets:
            return item
    for item in items:
        parts: list[str] = []
        for key in ("id", "name", "description", "context", "desc"):
            value = item.get(key)
            if value is not None:
                parts.append(str(value).strip())
        text = " ".join(parts).casefold()
        if q and q in text:
            return item
    return None


def _items(data: dict[str, Any], key: str) -> list[dict[str, Any]]:
    items = data.get(key)
    if not isinstance(items, list):
        return []
    return [item for item in items if isinstance(item, dict)]


def _event_datetime(value: dict[str, Any], tz: ZoneInfo) -> datetime | None:
    date_value = value.get("date")
    if date_value is None:
        return None
    time_value = value.get("time")
    if time_value is None:
        return None
    date = str(date_value).strip()
    if not date:
        return None
    time = str(time_value).strip()
    if not time:
        return None
    try:
        return datetime.strptime(f"{date} {time}", "%d.%m.%Y %H:%M").replace(tzinfo=tz)
    except ValueError:
        return None


def _rewards(value: object) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, list[str]] = {}
    for key in ("char", "arc", "item", "skin"):
        items = value.get(key)
        if not isinstance(items, list):
            continue
        cleaned = [str(item).strip() for item in items if item is not None and str(item).strip()]
        if cleaned:
            result[key] = cleaned
    return result


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_activity() -> str:
    """查询异环游戏活动日历。用户说"活动、活动日历、有什么活动、活动什么时候结束"时调用；
    按 UTC+8 当前时间分组，返回清洗后的中文 JSON。不需要用户账号。"""
    data = await _graphql(
        """
        query GetEvents {
          events {
            id
            type
            name
            start { date time }
            end { date time }
            rewards { char arc item skin }
            description
          }
        }
        """
    )
    tz = ZoneInfo("Asia/Shanghai")
    now = datetime.now(tz)
    ongoing: list[tuple[datetime, dict[str, object]]] = []
    upcoming: list[tuple[datetime, dict[str, object]]] = []
    ended: list[tuple[datetime, dict[str, object]]] = []
    for event in _items(data, "events"):
        start = _event_datetime(event["start"], tz) if isinstance(event.get("start"), dict) else None
        end = _event_datetime(event["end"], tz) if isinstance(event.get("end"), dict) else None
        event_id = event.get("id")
        name = event.get("name")
        if event_id is None or name is None:
            continue
        item: dict[str, object] = {
            "id": str(event_id).strip(),
            "name": str(name).strip(),
            "start": start.strftime("%Y-%m-%d %H:%M") if start is not None else "",
            "end": end.strftime("%Y-%m-%d %H:%M") if end is not None else "",
            "source": f"https://everness.info/zh-Hans/events/{event_id}",
        }
        rewards = _rewards(event.get("rewards"))
        if rewards:
            item["rewards"] = rewards
        if start is None or end is None:
            continue
        if now < start:
            item["status"] = "未开始"
            upcoming.append((start, item))
        elif now <= end:
            item["status"] = "进行中"
            ongoing.append((end, item))
        else:
            item["status"] = "已结束"
            ended.append((end, item))

    recent_cutoff = now - timedelta(days=30)
    ended_recent = [(end, item) for end, item in ended if end >= recent_cutoff]
    result = {
        "source": "https://everness.info/zh-Hans",
        "timezone": "UTC+8",
        "generated_at": now.strftime("%Y-%m-%d %H:%M:%S"),
        "note": "活动状态按 generated_at 计算；已结束只保留近 30 天，旧活动只计数。",
        "summary": {
            "ongoing": len(ongoing),
            "upcoming": len(upcoming),
            "ended_recent": len(ended_recent),
            "ended_older": len(ended) - len(ended_recent),
        },
        "ongoing": [item for _, item in sorted(ongoing, key=lambda row: row[0])],
        "upcoming": [item for _, item in sorted(upcoming, key=lambda row: row[0])],
        "ended_recent": [item for _, item in sorted(ended_recent, key=lambda row: row[0], reverse=True)],
    }
    return json.dumps(result, ensure_ascii=False, indent=2)


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_character(name: str) -> str:
    """查询异环角色详情、技能描述、觉醒、共鸣、生日、阵营、CV、基础属性。用户说"角色详情、角色背景、技能描述、觉醒、共鸣、生日、CV"时调用；
    注意：角色攻略/配装推荐不在这里，用 nte_guide。
    name 填角色名或别名，别名/谐音均可，后端会自动匹配，返回中文 JSON。不需要用户账号。"""
    CHARS.reload()
    char_id = CHARS.id_of(name)
    local_name = CHARS.name_by_id(char_id) if char_id is not None else None
    if char_id is None:
        data = await _graphql("query GetEspers { espers { id name element rarity } }")
        found = _pick(_items(data, "espers"), name)
        if found is None:
            return f"未在 Everness 找到角色：{name}"
        found_id = found.get("id")
        if found_id is None:
            return f"未在 Everness 找到角色：{name}"
        char_id = str(found_id).strip()
        if not char_id:
            return f"未在 Everness 找到角色：{name}"

    data = await _graphql(
        """
        query GetEsperById($id: String!) {
          esper(id: $id) {
            id
            name
            element
            rarity
            element_name
            weapon_type_id
            arcs_tags { id name icon type_id }
            char_tags { name icon }
            description
            introduction
            birthday
            abilityName
            faction
            voiceChinese
            voiceEnglish
            voiceJapanese
            voiceKorean
            hp
            atk
            def
            abilities {
              type_name
              name
              phases { title description shortDescription }
              additional_desc { name desc }
            }
            awaken { name desc type_name additional_desc { name desc } }
            resonance { name desc type_name additional_desc { name desc } }
            equip_slots { type_name desc special_desc ownerGridCount slots }
          }
        }
        """,
        {"id": char_id},
    )
    esper = data.get("esper")
    if not isinstance(esper, dict):
        return f"未在 Everness 找到角色：{name}"
    return json.dumps(
        {
            "local_name": local_name,
            "source": f"https://everness.info/zh-Hans/espers/{char_id}",
            "data": esper,
        },
        ensure_ascii=False,
        indent=2,
    )


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_drive_block(name: str) -> str:
    """查询异环驱动块、模块、core、套装效果。用户说"驱动块、模块、Module、core、主属性、副属性、套装效果"时调用；
    name 填驱动块名称，返回中文 JSON。不需要用户账号。"""
    data = await _graphql(
        """
        query GetShards {
          shards {
            id
            name
            icon
            quality
            type_id
            type_geometry
            ownGridNum
            main_stats { id name values icon }
            sub_stats { id name amount_stats icon }
            set_effect { setIcon conditions { condition desc } geometry { id name icon } }
          }
        }
        """
    )
    found = _pick(_items(data, "shards"), name)
    if found is None:
        return f"未在 Everness 找到驱动块：{name}"
    return json.dumps(
        {**found, "source": f"https://everness.info/zh-Hans/modules/{found['id']}"}, ensure_ascii=False, indent=2
    )


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_arc(name: str) -> str:
    """查询异环弧盘效果、属性、材料。用户说"弧盘、弧盘效果、弧盘材料、弧盘来源"时调用；
    name 填弧盘名或别名，返回中文 JSON。不需要用户账号。"""
    data = await _graphql(
        """
        query GetArcs {
          arcs {
            id
            name
            icon
            icon_small
            quality
            type_id
            type_icon
            weapon_type_id
            description
            context
            stats { id_stats name values bIsPercent icon }
            effect { name description values { id_value id_stats name icon bIsPercent values } }
            materials { items_id amount }
          }
        }
        """
    )
    found = _pick(_items(data, "arcs"), name)
    if found is None:
        return f"未在 Everness 找到弧盘：{name}"
    return json.dumps(
        {**found, "source": f"https://everness.info/zh-Hans/discs/{found['id']}"}, ensure_ascii=False, indent=2
    )


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_esper_cycle(name: str = "") -> str:
    """查询异环异能环合、元素组合、元素反应。用户说"异能环合、元素组合、元素反应、延滞、创生、覆纹、黯星、浊燃、浸染"时调用；
    name 填环合名或元素名，留空返回全部，返回中文 JSON。不需要用户账号。"""
    data = await _graphql(
        """
        query GetReactions {
          reactions {
            id
            name
            desc
            elements { id name icon }
            char_passive { id icon name_char type_name desc }
          }
        }
        """
    )
    reactions = _items(data, "reactions")
    if not name:
        return json.dumps(reactions, ensure_ascii=False, indent=2)
    found = _pick(reactions, name)
    if found is not None:
        return json.dumps(found, ensure_ascii=False, indent=2)

    q = name.casefold().strip()
    for reaction in reactions:
        elements = reaction.get("elements")
        if not isinstance(elements, list):
            continue
        if any(isinstance(item, dict) and q == str(item.get("name", "")).strip().casefold() for item in elements):
            return json.dumps(reaction, ensure_ascii=False, indent=2)
    return f"未在 Everness 找到异能环合：{name}"


@ai_tools(category="common", context_tags=["异环", "Everness"], capability_domain="异环资料库", timeout=30.0)
async def everness_search(keyword: str, category: str = "", limit: int = 20) -> str:
    """模糊搜索异环游戏资料。用户说"搜一下、查一下、不知道叫什么"时调用；
    keyword 填关键词；category 可填 角色、弧盘、驱动块、异能环合、道具、活动，留空搜索全部分类。
    返回匹配结果列表的中文 JSON。不需要用户账号。"""
    data = await _graphql(
        """
        query SearchEverness {
          espers { id name element rarity }
          arcs { id name quality type_id description }
          shards { id name quality type_id }
          reactions { id name desc elements { name } }
          items { id name quality type_id description context }
          events { id name type start { date time } end { date time } description }
        }
        """
    )
    groups = {
        "角色": ("espers", "espers", "角色 异能者 esper character"),
        "弧盘": ("arcs", "discs", "弧盘 arc disc"),
        "驱动块": ("shards", "modules", "驱动块 模块 module shard core"),
        "异能环合": ("reactions", "", "异能环合 esper cycle reaction 元素反应"),
        "道具": ("items", "items", "道具 物品 材料 item material"),
        "活动": ("events", "events", "活动 event calendar"),
    }
    selected = groups.items()
    if category:
        selected = [(label, value) for label, value in groups.items() if category.casefold() in value[2].casefold()]

    q = keyword.casefold().strip()
    count = min(max(limit, 1), 50)
    results: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    for label, (key, route, _) in selected:
        for item in _items(data, key):
            item_id_value = item.get("id")
            if item_id_value is None:
                continue
            item_id = str(item_id_value).strip()
            haystack = " ".join(str(value).strip() for value in item.values() if value is not None).casefold()
            if q and q not in haystack:
                continue
            identity = (key, item_id)
            if identity in seen:
                continue
            seen.add(identity)
            results.append(
                {
                    "category": label,
                    "id": item_id,
                    "name": item.get("name"),
                    "source": f"https://everness.info/zh-Hans/{route}/{item_id}"
                    if route
                    else "https://everness.info/zh-Hans",
                    "data": item,
                }
            )
            if len(results) >= count:
                return json.dumps(results, ensure_ascii=False, indent=2)
    return json.dumps(results, ensure_ascii=False, indent=2)
