from __future__ import annotations

from enum import Enum
from dataclasses import dataclass


class ScaleStat(str, Enum):
    """技能倍率挂靠的基础属性。倍率名后缀「防御力」「生命上限」决定挂靠对象，缺省挂攻击力。"""

    ATK = "atk"
    DEF = "def"
    HP = "hpmax"

    @property
    def label(self) -> str:
        return {ScaleStat.ATK: "攻击力", ScaleStat.DEF: "防御力", ScaleStat.HP: "生命上限"}[self]


@dataclass(frozen=True, slots=True, kw_only=True)
class PanelStats:
    """从真实游戏面板 properties 解出的最终战斗属性（已含角色自身常驻加成）。"""

    level: int
    atk: float
    defense: float
    hpmax: float
    crit_rate: float  # 0-1
    crit_dmg: float  # 0-1
    general_dmg: float  # 0-1 通用伤害增强
    element_dmg: float  # 0-1 角色元素「异能伤害增强」
    base_atk: float = 0.0  # 白值=角色基础攻+武器基础攻+突破base，仅外部攻击%Δ 增量用；缺省 0=退化旧行为

    def scale_value(self, scale: ScaleStat) -> float:
        if scale is ScaleStat.DEF:
            return self.defense
        if scale is ScaleStat.HP:
            return self.hpmax
        return self.atk


@dataclass(frozen=True, slots=True, kw_only=True)
class EnemyProfile:
    """敌人假设。资源里没有敌人数据，全部是带默认值的可配置假设。"""

    level: int
    resist: float = 0.0  # 敌人对该元素的抗性 0-1（可负）
    def_reduction: float = 0.0  # 减防（降低敌人防御）
    def_ignore: float = 0.0  # 无视防御
    res_reduction: float = 0.0  # 减抗 / 无视抗性


@dataclass(frozen=True, slots=True, kw_only=True)
class BuffBundle:
    """聚合后的外部增益（队伍 buff）。功能1 传全中性值，功能2 由解析出的全队 buff 汇总。"""

    atk_pct: float = 0.0  # 攻击力% 加成池（仅作用于攻击力挂靠）
    dmg_pct: float = 0.0  # 额外增伤（通用 / 元素，进增伤区）
    crit_rate: float = 0.0
    crit_dmg: float = 0.0
    def_ignore: float = 0.0
    res_ignore: float = 0.0


NEUTRAL_BUNDLE = BuffBundle()


@dataclass(frozen=True, slots=True, kw_only=True)
class SegmentDamage:
    """单个伤害倍率条目（一段普攻 / 一个技能命中）的结算结果。"""

    name: str
    pct: float  # 合计倍率%（已按模板把多段/多命中累加；固定值已并入下面三个结果）
    scale: ScaleStat
    non_crit: float
    crit: float
    expected: float


# 普攻里属于「一轮标准连段」的段名关键字；其余（下落 / 极限反击 / 瞄准）算情境技，不计入循环
_COMBO_KEYWORDS = ("一段", "二段", "三段", "四段", "五段", "六段", "七段")
# 情境段（按需才打）：下落/坠落/极限反击/闪避/瞄准。不含裸「极限」（过宽，会误吞具名段）。
_SITUATIONAL_KEYWORDS = ("下落", "坠落", "极限反击", "闪避", "瞄准")


@dataclass(frozen=True, slots=True, kw_only=True)
class AbilityDamage:
    """一个技能（普攻 / 战技 / 终结技 / 援护技）下的全部伤害倍率条目。"""

    ability_id: str
    type: str  # melee / skill / ultraskill / qte
    type_name: str
    name: str
    level: int
    segments: tuple[SegmentDamage, ...]

    @property
    def rotation_expected(self) -> float:
        """计入「一轮循环」的期望伤害：剔除情境段（下落/极限反击/瞄准）；多形态普攻连段（近战/远程/射弹/强力等
        不同前缀）**各形态都计入一轮求和**（旧版取最强一套会丢掉整条形态，安魂曲近战/远程少算近半）；
        非连段的具名输出段（分支/蓄力/具名招）同样计入一轮。"""

        def situational(seg: SegmentDamage) -> bool:
            return any(key in seg.name for key in _SITUATIONAL_KEYWORDS)

        if self.type == "melee":
            combo = [seg for seg in self.segments if any(key in seg.name for key in _COMBO_KEYWORDS)]
            forms: dict[str, float] = {}
            for seg in combo:
                prefix = seg.name
                for key in _COMBO_KEYWORDS:
                    prefix = prefix.replace(key, "")
                forms[prefix] = forms.get(prefix, 0.0) + seg.expected
            best_combo = sum(forms.values())
            extra = sum(
                seg.expected
                for seg in self.segments
                if not any(key in seg.name for key in _COMBO_KEYWORDS) and not situational(seg)
            )
            return best_combo + extra
        return sum(seg.expected for seg in self.segments if not situational(seg))

    @property
    def combo_form_count(self) -> int:
        """普攻连段的不同形态数（近战/远程/强力/射弹等不同前缀）。>1 表示 rotation_expected 是多形态求和，
        供卡片标注「Σ多形态」——这些角色的循环期望按全形态打满累加（如安魂曲近战+远程轮换）。"""
        if self.type != "melee":
            return 0
        forms: set[str] = set()
        for seg in self.segments:
            if not any(key in seg.name for key in _COMBO_KEYWORDS):
                continue
            prefix = seg.name
            for key in _COMBO_KEYWORDS:
                prefix = prefix.replace(key, "")
            forms.add(prefix)
        return len(forms)


@dataclass(frozen=True, slots=True, kw_only=True)
class DamageContext:
    """本次结算用到的乘区拆解，供卡片展示「倍率拆解」。"""

    panel: PanelStats
    enemy: EnemyProfile
    dmg_bonus_mult: float  # 增伤区
    crit_expected_mult: float  # 暴击区（期望）
    def_mult: float  # 防御区
    res_mult: float  # 抗性区


@dataclass(frozen=True, slots=True, kw_only=True)
class CharacterDamage:
    """单角色完整伤害结算：各技能伤害 + 乘区上下文。"""

    character_id: str
    abilities: tuple[AbilityDamage, ...]
    context: DamageContext
