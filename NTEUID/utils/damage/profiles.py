from __future__ import annotations

import re
import json
from functools import lru_cache
from dataclasses import replace, dataclass
from collections.abc import Sequence

from .raw import RawCharData
from .buffs import ParsedBuff, bundle_from, segment_mult, resonance_effects, bundle_for_segment
from .models import (
    NEUTRAL_BUNDLE,
    ScaleStat,
    BuffBundle,
    PanelStats,
    EnemyProfile,
    AbilityDamage,
    DamageContext,
    CharacterDamage,
)
from .formula import (
    compute_segment,
    crit_multipliers,
    defense_multiplier,
    resistance_multiplier,
    damage_bonus_multiplier,
)
from .constants import (
    PROP_ATK,
    PROP_DEF,
    PROP_CRIT,
    PROP_HPMAX,
    PROP_CRIT_DMG,
    PROP_DMG_GENERAL,
    element_dmg_prop,
)
from ..sdk.tajiduo_model import CharacterDetail
from ..resource.RESOURCE_PATH import STATIC_RESOURCE_PATH

_CHAR_DATA_PATH = STATIC_RESOURCE_PATH / "data" / "char"

# 战斗技能展示顺序：普攻 → 战技 → 终结技 → 援护技
_TYPE_ORDER = {"melee": 0, "skill": 1, "ultraskill": 2, "qte": 3}
# 倍率名里含这些词的是治疗 / 护盾，不挂攻击伤害，排除出直伤
_NON_DAMAGE_KEYWORDS = ("治疗", "护盾", "回复", "恢复")
# 倍率模板里的占位项：{idx} 后可带 % 与 *倍数
_TERM_RE = re.compile(r"\{(\d+)\}(%?)(?:\*(\d+))?")
_LITERAL_RE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*(%?)\s*$")


@dataclass(frozen=True, slots=True)
class _AbilityStat:
    name: str
    value_name: str
    values: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class _AbilityProfile:
    ability_id: str
    type: str
    type_name: str
    name: str
    damage_stats: tuple[_AbilityStat, ...]


def _is_damage_stat(name: str, value_name: str) -> bool:
    if "%" not in value_name or "倍率" not in name:
        return False
    return not any(keyword in name for keyword in _NON_DAMAGE_KEYWORDS)


@lru_cache(maxsize=64)
def load_ability_profiles(char_id: str) -> dict[str, _AbilityProfile]:
    """读 resource/data/char/<id>.json 的 abilities，按小写技能 id 建表（与面板 skill.id 对齐）。"""
    path = _CHAR_DATA_PATH / f"{char_id}.json"
    if not path.exists():
        return {}
    raw = RawCharData.model_validate_json(path.read_text(encoding="utf-8"))
    profiles: dict[str, _AbilityProfile] = {}
    for ability in raw.abilities:
        damage_stats = tuple(
            _AbilityStat(
                name=stat.name,
                value_name=stat.value_name,
                values=tuple(tuple(arr) for arr in stat.values),
            )
            for stat in ability.stats
            # 必须随等级成长(values 非空)：剔除海月「射弹强化倍率=70%」这类字面量强化系数(values=null)，是 buff 非直伤段
            if _is_damage_stat(stat.name, stat.value_name) and stat.values
        )
        profiles[ability.id.lower()] = _AbilityProfile(
            ability_id=ability.id,
            type=ability.type,
            type_name=ability.type_name,
            name=ability.name,
            damage_stats=damage_stats,
        )
    return profiles


def _eval_template(stat: _AbilityStat, level_idx: int) -> tuple[float, float, ScaleStat]:
    """把倍率模板在指定技能等级下求值，返回 (合计%, 合计固定值, 挂靠属性)。"""
    scale = ScaleStat.ATK
    text = stat.value_name
    if "防御力" in text:
        scale = ScaleStat.DEF
        text = text.replace("防御力", "")
    elif "生命上限" in text or "生命值" in text:
        scale = ScaleStat.HP
        text = text.replace("生命上限", "").replace("生命值", "")
    text = text.replace("每段", "")

    pct = 0.0
    flat = 0.0
    terms = list(_TERM_RE.finditer(text))
    for term in terms:
        idx = int(term.group(1))
        if idx >= len(stat.values):
            continue
        arr = stat.values[idx]
        if not arr:
            continue
        value = arr[min(level_idx, len(arr) - 1)] * int(term.group(3) or 1)
        if term.group(2) == "%":
            pct += value
        else:
            flat += value
    if not terms:
        literal = _LITERAL_RE.match(text)
        if literal is not None:
            value = float(literal.group(1))
            if literal.group(2) == "%":
                pct += value
            else:
                flat += value
    return pct, flat, scale


@lru_cache(maxsize=64)
def _atk_base_curve(char_id: str) -> tuple[float, ...]:
    """角色基础攻随等级曲线（resource char json 的 AtkBase）。RawCharData 不含 stats，故轻量直读。"""
    path = _CHAR_DATA_PATH / f"{char_id}.json"
    if not path.exists():
        return ()
    data = json.loads(path.read_text(encoding="utf-8"))
    for stat in data.get("stats", []):
        if stat.get("id_stats") == "AtkBase":
            return tuple(float(v) for v in stat.get("values", []))
    return ()


def _structured_atk(character: CharacterDetail) -> tuple[float, float]:
    """面板里已聚合的结构化攻击%（武器 + 驱动 atkup 主副词条，分数）与固定攻（驱动 atkadd）。
    用于反解白值，**不**作为增益（这些已在面板 atk 里）。"""
    pct = 0.0
    flat = 0.0
    for prop in character.fork.properties:
        if prop.value and prop.id.lower() == "atkup":
            pct += _parse_value(prop.value)
    for item in (*character.suit.core, *character.suit.pie):
        for prop in (*item.main_properties, *item.properties):
            if not prop.value:
                continue
            key = prop.id.lower()
            if key == "atkup":
                pct += _parse_value(prop.value)
            elif key == "atkadd":
                flat += _parse_value(prop.value)
    return pct, flat


def _white_atk(character: CharacterDetail, panel_atk: float) -> float:
    """白值=角色基础攻+武器基础攻+突破base。突破base 无字段，用 (面板攻-结构化flat)/(1+结构化攻%)
    反解。反解须≥naive(突破≥0)才采信；否则装备数据脏 → 退回 naive（白值下界，绝不高估外部Δ%增量）。"""
    curve = _atk_base_curve(character.id)
    char_base = curve[min(max(character.alev - 1, 0), len(curve) - 1)] if curve else 0.0
    fork_props = {prop.id.lower(): prop.value for prop in character.fork.properties}
    weapon_base = _parse_value(fork_props["atkbase"]) if fork_props.get("atkbase") else 0.0
    naive = char_base + weapon_base
    struct_pct, struct_flat = _structured_atk(character)
    implied = (panel_atk - struct_flat) / (1.0 + struct_pct) if (1.0 + struct_pct) else naive
    return implied if implied >= naive else naive


def parse_panel(character: CharacterDetail) -> PanelStats:
    """从真实面板 properties 解出最终战斗属性。元素增伤取角色自身元素那一条。"""
    props = {prop.id: prop.value for prop in character.properties}
    atk_value = _parse_value(props[PROP_ATK])
    return PanelStats(
        level=character.alev,
        atk=atk_value,
        defense=_parse_value(props[PROP_DEF]),
        hpmax=_parse_value(props[PROP_HPMAX]),
        crit_rate=_parse_value(props[PROP_CRIT]),
        crit_dmg=_parse_value(props[PROP_CRIT_DMG]),
        general_dmg=_parse_value(props[PROP_DMG_GENERAL]),
        element_dmg=_parse_value(props[element_dmg_prop(character.element_type)]),
        base_atk=_white_atk(character, atk_value),
    )


def _build_context(panel: PanelStats, enemy: EnemyProfile, bundle: BuffBundle) -> DamageContext:
    expected_crit, _ = crit_multipliers(panel.crit_rate + bundle.crit_rate, panel.crit_dmg + bundle.crit_dmg)
    return DamageContext(
        panel=panel,
        enemy=enemy,
        dmg_bonus_mult=damage_bonus_multiplier(panel, bundle),
        crit_expected_mult=expected_crit,
        def_mult=defense_multiplier(panel.level, enemy, bundle.def_ignore),
        res_mult=resistance_multiplier(enemy, bundle.res_ignore),
    )


def _segment_bundle(
    bundle: BuffBundle,
    scoped_buffs: Sequence[ParsedBuff],
    element: str,
    ability_type: str,
    ability_name: str,
    segment_name: str,
) -> BuffBundle:
    """全局 bundle + 命中本段的来源限定增益。来源限定只叠 dmg_pct/crit_rate/crit_dmg，
    攻击力%/无视防御/无视抗恒沿用全局（这三项不存在来源限定形态）。"""
    if not scoped_buffs:
        return bundle
    extra = bundle_for_segment(scoped_buffs, element, ability_type, ability_name, segment_name)
    if not (extra.dmg_pct or extra.crit_rate or extra.crit_dmg):
        return bundle
    return replace(
        bundle,
        dmg_pct=bundle.dmg_pct + extra.dmg_pct,
        crit_rate=bundle.crit_rate + extra.crit_rate,
        crit_dmg=bundle.crit_dmg + extra.crit_dmg,
    )


# 共鸣1「技能等级提升N级」点名的技能 → 对应 ability.type +N。文案有两种形态：
#   前缀式「极轨终结：奥义·X」（多数角色）与 纯技能名「奇零除尽」（异能者·零）。
# 两者都要命中，故用「类型前缀关键词」OR「ability.name 归一化命中」双判定。
_TYPE_KEYWORD: dict[str, str] = {
    "melee": "普通攻击",
    "skill": "变轨技能",
    "ultraskill": "极轨终结",
    "qte": "援护技",
}
_SKILL_LEVEL_UP_RE = re.compile(r"技能等级提升\s*(\d+)\s*级")


def _norm_skill_text(text: str) -> str:
    """去标签 + 去括号/空白，消除文案与 ability.name 间的标点差异（『』vs「」、奥义· X 的空格）。"""
    return re.sub(r"[「」『』【】《》\s]", "", re.sub(r"<[^>]+>", "", text))


def _resonance_skill_bonus(character: CharacterDetail, profiles: dict[str, _AbilityProfile]) -> dict[str, int]:
    """共鸣1「技能等级提升N级」对各技能类型(ability.type)的等级加成。

    面板 skill.level 是玩家投入的技能等级，不含共鸣的隐藏 +N（实测觉6 角色面板各技能仍显示
    投入等级），结算倍率时必须补回，否则觉≥3 角色被低估。觉醒未达 awaken_num 的共鸣不计。
    """
    bonus: dict[str, int] = {}
    for desc, awaken_num in resonance_effects(character.id):
        if character.awaken_lev < awaken_num:
            continue
        clean = re.sub(r"<[^>]+>", "", desc)
        match = _SKILL_LEVEL_UP_RE.search(clean)
        if match is None:  # 该条共鸣不是「技能等级提升」型（如小吱的金谷效率）
            continue
        levels = int(match.group(1))
        norm_desc = _norm_skill_text(desc)
        for profile in profiles.values():
            keyword = _TYPE_KEYWORD.get(profile.type)
            if keyword is None:  # 仅 melee/skill/ultraskill/qte 计入，跳过 passive/city
                continue
            if keyword in norm_desc or (profile.name and _norm_skill_text(profile.name) in norm_desc):
                bonus[profile.type] = max(bonus.get(profile.type, 0), levels)
    return bonus


def build_character_damage(
    character: CharacterDetail,
    enemy: EnemyProfile,
    bundle: BuffBundle = NEUTRAL_BUNDLE,
    scoped_buffs: Sequence[ParsedBuff] = (),
) -> CharacterDamage:
    """单角色完整伤害结算：真实面板 × 真实倍率表 × 乘区公式。

    scoped_buffs 为带 scope 的来源限定增益（如「极轨终结」造成的伤害+X%）：逐段按 ability.type/name
    匹配后只折给对应段，不平摊到全部段。默认空 = 仅全局 bundle（行为与旧版完全一致）。
    """
    panel = parse_panel(character)
    profiles = load_ability_profiles(character.id)
    element = character.element_type.label
    skill_bonus = _resonance_skill_bonus(character, profiles)

    abilities: list[AbilityDamage] = []
    for skill in character.skills:
        if skill.type == "Passive" or not skill.id:
            continue
        profile = profiles.get(skill.id.lower())
        if profile is None or not profile.damage_stats:
            continue
        level_idx = max(0, skill.level - 1) + skill_bonus.get(profile.type, 0)
        segments_list = []
        for stat in profile.damage_stats:
            pct, flat, scale = _eval_template(stat, level_idx)
            if not (pct or flat):
                continue
            pct *= 1.0 + segment_mult(scoped_buffs, stat.name)  # 倍率提升型增益（基础伤害区）
            seg_bundle = _segment_bundle(bundle, scoped_buffs, element, profile.type, profile.name, stat.name)
            segments_list.append(
                compute_segment(
                    name=stat.name, pct=pct, flat=flat, scale=scale, panel=panel, enemy=enemy, bundle=seg_bundle
                )
            )
        segments = tuple(segments_list)
        if not segments:
            continue
        abilities.append(
            AbilityDamage(
                ability_id=profile.ability_id,
                type=profile.type,
                type_name=profile.type_name,
                name=profile.name or skill.name,
                level=skill.level,
                segments=segments,
            )
        )

    abilities.sort(key=lambda ability: _TYPE_ORDER.get(ability.type, 99))
    return CharacterDamage(
        character_id=character.id,
        abilities=tuple(abilities),
        context=_build_context(panel, enemy, bundle),
    )


def build_member_damage(
    character: CharacterDetail,
    enemy: EnemyProfile,
    member_buffs: Sequence[ParsedBuff],
) -> tuple[CharacterDamage, BuffBundle]:
    """成员伤害单一入口：从同一份 member_buffs 同时派生全局 bundle 与逐段来源限定增益，
    杜绝「全局 bundle 与 scoped_buffs 来自不同列表」的静默错位。返回 (伤害, 全局 bundle)；
    bundle 供环合暴伤区等复用。元素自取，调用方无需再传。"""
    bundle = bundle_from(member_buffs, character.element_type.label)
    return build_character_damage(character, enemy, bundle, scoped_buffs=member_buffs), bundle


def _parse_value(value: str) -> float:
    raw = value.strip()
    if raw.endswith("%"):
        return float(raw[:-1]) / 100.0
    return float(raw)
