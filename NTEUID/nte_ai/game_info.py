from __future__ import annotations

import re

from pydantic import Field, BaseModel, RootModel, ConfigDict, ValidationError

from gsuid_core.logger import logger
from gsuid_core.ai_core.models import KnowledgePoint
from gsuid_core.ai_core.register import ai_alias, ai_entity

from ..nte_role.score import load_attributes, load_score_plan
from ..utils.damage.raw import RawEffect, RawCharData
from ..utils.name_convert import CHARS
from ..utils.resource.RESOURCE_PATH import CHAR_META_PATH, STATIC_RESOURCE_PATH


class _CharMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    aliases: list[str] = Field(default_factory=list)


class _CharMetaFile(RootModel[dict[str, _CharMeta]]):
    pass


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", text).replace("\r", "\n")).strip()


def _ability_lines(char: RawCharData) -> list[str]:
    order = {"melee": 0, "skill": 1, "ultraskill": 2, "qte": 3, "passive": 4, "peculiarity": 5, "city": 6}
    lines: list[str] = []
    for ability in sorted(char.abilities, key=lambda item: order[item.type] if item.type in order else 99):
        if not ability.name:
            continue
        desc = _clean(ability.phases[0].description) if ability.phases else ""
        lines.append(f"- {ability.type_name}：{ability.name}" + (f"。{desc}" if desc else ""))
    return lines


def _effect_lines(title: str, effects: list[RawEffect]) -> list[str]:
    lines: list[str] = []
    for index, effect in enumerate(effects, start=1):
        desc = _clean(effect.desc)
        if not effect.name and not desc:
            continue
        suffix = f"(觉{effect.awaken_num})" if effect.awaken_num else ""
        lines.append(f"- {title}{index}{suffix}：{effect.name}。{desc}")
    return lines


def _attr_names(attr_ids: frozenset[str]) -> str:
    attrs = load_attributes().entries
    names = (attrs[attr_id].name for attr_id in sorted(attr_ids) if attr_id in attrs and attrs[attr_id].name)
    return "、".join(dict.fromkeys(names))


def _score_line(char_id: str) -> str:
    plan = load_score_plan(char_id)
    if plan is None:
        return ""
    core = _attr_names(plan.core_main_attrs)
    recommend = _attr_names(plan.recommend_attrs)
    lines = [f"评分参考分：{plan.refer_score}"]
    if core:
        lines.append(f"核心主词条：{core}")
    if recommend:
        lines.append(f"推荐有效词条：{recommend}")
    return "\n".join(lines)


def _char_content(char_id: str, meta: _CharMeta) -> str | None:
    path = STATIC_RESOURCE_PATH / "data" / "char" / f"{char_id}.json"
    if not path.exists():
        return None
    char = RawCharData.model_validate_json(path.read_text(encoding="utf-8"))
    lines = [
        f"{char.name if char.name else meta.name} 是异环角色，{char.rarity}星，{char.element_name}属性，弧系为{char.arcs_name}。",
        f"简介：{_clean(char.introduction)}",
        f"资源表满级基础属性：生命 {char.hp} / 攻击 {char.atk} / 防御 {char.def_}",
        "技能：",
        *_ability_lines(char),
    ]
    for title, content in (
        ("觉醒", _effect_lines("觉醒", char.awaken)),
        ("混频共鸣", _effect_lines("共鸣", char.resonance)),
        ("养成评分", [_score_line(char_id)]),
    ):
        if content and content[0]:
            lines.extend([f"{title}：", *content])
    return "\n".join(lines)


def register_game_info() -> None:
    ai_entity(
        KnowledgePoint(
            id="nteuid-yihuan-game",
            plugin="NTEUID",
            title="异环游戏信息",
            content="异环是都市开放世界游戏。NTEUID 可查询账号面板、角色面板、练度、实时体力、签到、抽卡统计、攻略图。",
            tags=["异环", "账号面板", "角色面板", "练度", "体力"],
        )
    )
    if not CHAR_META_PATH.exists():
        logger.warning("[NTE AI] 角色元数据文件不存在，跳过角色知识库和别名注册；请先同步资源数据")
        return

    try:
        metas = _CharMetaFile.model_validate_json(CHAR_META_PATH.read_text(encoding="utf-8")).root
    except ValidationError as error:
        logger.warning(f"[NTE AI] 角色元数据解析失败: {error!r}")
        return

    CHARS.reload()
    for char_id, meta in metas.items():
        if not meta.name:
            continue
        aliases = CHARS.aliases_of(meta.name)
        if not aliases:
            aliases = [*meta.aliases, meta.name]
        ai_alias(meta.name, aliases, scope="NTEUID")
        try:
            content = _char_content(char_id, meta)
        except ValidationError as error:
            logger.warning(f"[NTE AI] 角色资源解析失败: char_id={char_id} error={error!r}")
            continue
        if content is None:
            continue
        ai_entity(
            KnowledgePoint(
                id=f"nteuid-yihuan-char-{char_id}",
                plugin="NTEUID",
                title=f"异环角色资料 - {meta.name}",
                content=content,
                tags=["异环", "角色", char_id, meta.name, *aliases],
            )
        )
