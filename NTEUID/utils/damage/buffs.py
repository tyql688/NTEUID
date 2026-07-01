from __future__ import annotations

import re
from typing import TypeVar, Protocol
from functools import lru_cache
from dataclasses import dataclass
from collections.abc import Iterable, Sequence

from .raw import RawCharData, RawForkData
from .models import BuffBundle
from .scopes import extract_scope, scope_matches, is_orphan_damage
from ..sdk.tajiduo_model import CharacterFork, CharacterDetail
from ..resource.RESOURCE_PATH import STATIC_RESOURCE_PATH


class _Keyed(Protocol):
    @property
    def kind(self) -> str: ...
    @property
    def value(self) -> float: ...
    @property
    def text(self) -> str: ...


_T = TypeVar("_T", bound=_Keyed)

_FORK_DATA_PATH = STATIC_RESOURCE_PATH / "data" / "fork"
_CHAR_DATA_PATH = STATIC_RESOURCE_PATH / "data" / "char"

_TAG_RE = re.compile(r"<[^>]+>")
_PLACEHOLDER_RE = re.compile(r"\{(\d+)\}")
_SENTENCE_RE = re.compile(r"[。\n\r；;]")

# 队友范围词。「全体」单独出现常指「全体目标 / 敌方全体」=敌人，须排除敌人范围词。
_TEAM_TOKENS = ("全队", "全体")
_ENEMY_SCOPE_TOKENS = ("目标", "敌")
# 「基于自身基础攻击力」这类按支援者基础攻击力换算的加成，机制特殊，不自动折算。
_SKIP_TOKEN = "基础攻击力"

# 自身增益只认「条件触发型」：战斗中触发的 buff 必不在出战面板里，加它不会与面板重复计算；
# 无触发词的常驻增益（如武器「攻击力提高X%」）默认已计入面板，跳过以避免双计。
_SELF_TRIGGERS = (
    "释放",
    "施放",
    "命中",
    "暴击",
    "每次",
    "每层",
    "叠加",
    "闪避",
    "弹反",
    "承轨",
    "站场",
    "后台",
    "当前控制",
    "持有",
    "受到",
    "攻击时",
    "攻击后",
    "boss",
    "Boss",
    "破碎",
    "破韧",
    "低于",
    "高于",
    "延滞",
    "浸染",
    "蓄",
    "失去生命",
)

# 攻击力%识别：必须有增益动词贴着「攻击力」，否则「X%攻击力的伤害」这类伤害系数会被误判成加攻。
_ATK_RES = (
    re.compile(r"攻击力(?:提升|提高)(\d+(?:\.\d+)?)%"),  # 攻击力提升X%
    re.compile(r"(?:提升|提高|获得|增加)(\d+(?:\.\d+)?)%攻击力"),  # 提升/获得X%攻击力
    re.compile(r"(\d+(?:\.\d+)?)%攻击力(?:提升|提高|加成)"),  # X%攻击力提升/加成
)
# 暴伤 / 暴击率：数值可在词后（暴击伤害提高6%）或词前（12%暴击伤害提升）；动词含 增加。
_CRIT_DMG_RE = re.compile(r"暴击伤害(?:提升|提高|增加)(\d+(?:\.\d+)?)%|(\d+(?:\.\d+)?)%暴击伤害(?:提升|提高|增加)")
_CRIT_RATE_RE = re.compile(r"暴击率(?:提升|提高|增加)(\d+(?:\.\d+)?)%|(\d+(?:\.\d+)?)%暴击率(?:提升|提高|增加)")
# 通用增伤：覆盖 造成的伤害/造成伤害(无的)/技能伤害/通用伤害/增伤/伤害加成 + (额外)?提升|提高|增加。
# alt2 收裸引号源限定伤害「『X』(的)伤害提升Y%」(无「造成」前缀，如薄荷变轨/埃德嘉狂流)——靠紧邻
# 闭引号 [」』] 锚定，不误吃描述句。数字前 \s* 容忍「提升 8%」这类空格(九原致命玫约)。
# **不**含「提升至」——那是「设为X%」(becomes)非「+X%」，旧版当 +X% 会爆量高估，剔除。
_DMG_RE = re.compile(
    r"(?:造成的?伤害|通用伤害|技能伤害|增伤|伤害加成)(?:（[^）]*）)?(?:额外)?(?:提升|提高|增加)\s*(\d+(?:\.\d+)?)%"
    r"|[」』]的?伤害(?:提升|提高)\s*(\d+(?:\.\d+)?)%"
)
# 元素限定增伤（X属性异能伤害提升Y%）。带元素字 → 仅施加给同元素成员（异环角色单元素，对其全段成立）。
_ELEM_DMG_RE = re.compile(r"([光灵咒暗魂相])属性异能伤害(?:提升|提高|增加)(\d+(?:\.\d+)?)%")
# 伤害「描述」非增益（额外伤害段 / 造成 N 次 X%攻击力的伤害）→ 不当作增益、不 surface。
_DAMAGE_DESC_RE = re.compile(
    r"\d+(?:\.\d+)?%\s*\*?\s*(?:攻击力|防御力|生命上限)的|额外造成|承受额外|(?:造成|受到|承受)\s*\d+\s*次"
)
# 倍率提升型增益（伤害倍率 = 原始倍率 ×(1+提升)，进基础伤害区，**非**增伤区）。
# 「技能名」…伤害倍率提升X%；非贪婪且不跨子句(，)，只取紧邻 伤害倍率 的那个引号名。
# 「提升至…」是设定额外伤害段(零的铭隙鉴刻)，不是 +%，靠 (?:提升|提高)\s*\d 天然排除(后接「至」不匹配)。
_MULT_RE = re.compile(r"[「『]([^」』]+)[」』][^。；，]*?伤害倍率(?:提升|提高)\s*(\d+(?:\.\d+)?)\s*%")


def _atk_pct(sentence: str) -> float | None:
    for pattern in _ATK_RES:
        found = pattern.search(sentence)
        if found is not None:
            return float(found.group(1))
    return None


# 用于「看着像 buff 却没解析出」的显式 surface 判定
_BUFFY_TOKENS = ("攻击力", "暴击", "暴伤", "伤害", "增伤")

# 敌人减益规则：任意句子都搜（减防 / 减抗对全队同样生效）。双向语序——动词在前（抗性降低X%）或
# 数值在前（降低…X%…抗性，如翳「降低其锁定目标2%的相异能属性抗性」）。
# 填充段 stop-set 含顿号「、」：阻止跨枚举项偷数（阿德勒「攻击力降低20%、属性抗性降低10%」backward 若不挡
# 顿号会把 20% 偷给抗性，实际应 10%）。[^，。；、] 同时卡子句和并列项。
_ENEMY_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"防御力?(?:下降|降低|减少)\s*(\d+(?:\.\d+)?)%|(?:下降|降低|减少)[^，。；、]{0,6}?(\d+(?:\.\d+)?)%[^，。；、]{0,6}防御"
        ),
        "def_reduction",
    ),
    (
        re.compile(
            r"抗性(?:下降|降低|减少)\s*(\d+(?:\.\d+)?)%|(?:下降|降低|减少)[^，。；、]{0,6}?(\d+(?:\.\d+)?)%[^，。；、]{0,8}抗性"
        ),
        "res_reduction",
    ),
)
# 无视防御 / 无视抗：攻击者侧、仅装备者自身生效，且必不在出战面板里 → 当作自身增益，无需触发门控。
# 双向 + 中间填充词（无视目标10%的防御力 / 12%无视防御效果 / 一次性消耗…12%无视防御）。顿号同样入 stop-set。
_IGNORE_RULES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"无视[^，。；、]{0,4}?(\d+(?:\.\d+)?)%[^，。；、]{0,4}?防御|(\d+(?:\.\d+)?)%[^，。；、]{0,2}无视[^，。；、]{0,2}防御"
        ),
        "def_ignore",
    ),
    (
        re.compile(
            r"无视[^，。；、]{0,4}?(\d+(?:\.\d+)?)%[^，。；、]{0,8}?抗性|(\d+(?:\.\d+)?)%[^，。；、]{0,2}无视[^，。；、]{0,8}抗性"
        ),
        "res_ignore",
    ),
)


def _first_num(match: re.Match[str]) -> float:
    """多分支正则取第一个非空数字组（双向语序各占一组）。"""
    for group in match.groups():
        if group is not None:
            return float(group)
    return 0.0


@dataclass(frozen=True, slots=True)
class ParsedBuff:
    kind: str  # atk_pct / dmg_pct / crit_rate / crit_dmg
    value: float  # 比例（0.15 = 15%）
    source: str  # 套装4件 / 武器 / 技能 / 觉醒 / 共鸣
    text: str
    element: str = ""  # 非空=元素限定增伤（光/灵/咒/暗/魂/相），仅施加给同元素成员
    scope: str = ""  # 非空=来源限定（type:/ability:/segment:），只折给匹配的伤害段，与 element 正交


@dataclass(frozen=True, slots=True)
class EnemyDebuff:
    kind: str  # def_reduction / res_reduction
    value: float
    source: str
    text: str


@dataclass(frozen=True, slots=True)
class BuffScan:
    owner: str
    team_buffs: tuple[ParsedBuff, ...]  # 全队增益（施给所有成员）
    self_buffs: tuple[ParsedBuff, ...]  # 仅装备者自身、条件触发型增益
    enemy_debuffs: tuple[EnemyDebuff, ...]
    unparsed: tuple[str, ...]  # 像 buff 但解析失败的句子
    orphans: tuple[str, ...] = ()  # 明确是伤害增益但无对应倍率段（附着/持续/心灵），诚实 surface 不入算


def _clean(text: str) -> str:
    return _TAG_RE.sub("", text)


def _is_team_scope(sentence: str) -> bool:
    """句子是否在给队友加成。「全队」恒为队友；「全体」需排除「全体目标 / 敌方全体」这类敌人范围。"""
    if not any(token in sentence for token in _TEAM_TOKENS):
        return False
    if "全队" in sentence:
        return True
    return not any(token in sentence for token in _ENEMY_SCOPE_TOKENS)


def _extract_stats(sentence: str) -> list[tuple[str, float, str, str]]:
    """返回 (kind, 值, 元素, 作用域)。

    - 攻击力%：恒全局（真实数据无来源限定的加攻），element/scope 均空。
    - 暴击率/暴伤：scope = extract_scope(句子)——来源限定（如「极轨终结」暴击率）只折给该 type 段，
      全局暴击（scope=""）照常进面板暴击区。
    - 元素限定增伤（X属性异能伤害+Y%）：带元素字、scope 空，与 scope 正交（由 bundle_from 按成员元素施加）。
    - 其余通用增伤：scope = extract_scope(句子)，"" = 全局，type:/ability:/segment: = 来源限定。
    """
    # 注：增益按**单层基础值**计，不按「至多叠加N层」自动 ×N——同一句里 N 层常只属某子效果（如哈尼娅
    # 「魂属性+12%，且每次普攻…最多叠加10层」的 10 层并不作用于那 12% 基础值），盲乘会爆量高估，故保守取单层。
    hits: list[tuple[str, float, str, str]] = []
    if _SKIP_TOKEN not in sentence:
        atk = _atk_pct(sentence)
        if atk is not None:
            hits.append(("atk_pct", atk / 100.0, "", ""))
    scope = extract_scope(sentence)
    crit_rate = _crit_value(_CRIT_RATE_RE, sentence)
    if crit_rate is not None:
        hits.append(("crit_rate", crit_rate / 100.0, "", scope))
    crit_dmg = _crit_value(_CRIT_DMG_RE, sentence)
    if crit_dmg is not None:
        hits.append(("crit_dmg", crit_dmg / 100.0, "", scope))
    elem = _ELEM_DMG_RE.search(sentence)
    if elem is not None:
        # 元素限定 → 带元素字；若同时源限定（『变轨/终结』造成的X属性异能伤害）也带上 scope，否则空=全局元素增伤。
        hits.append(("dmg_pct", float(elem.group(2)) / 100.0, elem.group(1), scope))
        return hits
    dmg = _DMG_RE.search(sentence)
    if dmg is not None:
        hits.append(("dmg_pct", _first_num(dmg) / 100.0, "", scope))
    return hits


def _crit_value(pattern: re.Pattern[str], sentence: str) -> float | None:
    """暴击正则两路捕获（数值在词后或词前），返回命中的那一组。"""
    found = pattern.search(sentence)
    if found is None:
        return None
    raw = found.group(1) or found.group(2)
    return float(raw) if raw else None


def _resolve_fork_effect(fork: CharacterFork) -> str:
    """武器特效文案：用资源里的描述模板 + 面板 lbd（玩家实际精炼数值）填占位符。"""
    if not fork.id:
        return ""
    path = _FORK_DATA_PATH / f"{fork.id}.json"
    if not path.exists():
        return ""
    desc = RawForkData.model_validate_json(path.read_text(encoding="utf-8")).effect.description
    if not desc:
        return ""
    lbd = fork.lbd

    def _sub(match: re.Match[str]) -> str:
        index = int(match.group(1))
        return lbd[index] if index < len(lbd) else match.group(0)

    return _PLACEHOLDER_RE.sub(_sub, desc)


@lru_cache(maxsize=64)
def _skill_texts(char_id: str) -> tuple[str, ...]:
    """战技 / 终结技 / 被动的描述文案，用于扫描技能型增益。"""
    path = _CHAR_DATA_PATH / f"{char_id}.json"
    if not path.exists():
        return ()
    raw = RawCharData.model_validate_json(path.read_text(encoding="utf-8"))
    return tuple(
        phase.description
        for ability in raw.abilities
        if ability.type in {"skill", "ultraskill", "passive"}
        for phase in ability.phases
        if phase.description
    )


@lru_cache(maxsize=64)
def _awaken_texts(char_id: str) -> tuple[str, ...]:
    """觉醒6条全量描述。**保持下标对齐**（EffectN→awaken[N-1]），不能按 desc 过滤。"""
    path = _CHAR_DATA_PATH / f"{char_id}.json"
    if not path.exists():
        return ()
    raw = RawCharData.model_validate_json(path.read_text(encoding="utf-8"))
    return tuple(a.desc for a in raw.awaken)


@lru_cache(maxsize=64)
def resonance_effects(char_id: str) -> tuple[tuple[str, int], ...]:
    """共鸣条目 (描述, 解锁所需觉醒等级 awaken_num)。共鸣1=觉3(技能等级提升)、共鸣2=觉6(战斗增益)。
    按 awaken_num 解锁（**不是**按列表前 slev 个切片）。"""
    path = _CHAR_DATA_PATH / f"{char_id}.json"
    if not path.exists():
        return ()
    raw = RawCharData.model_validate_json(path.read_text(encoding="utf-8"))
    return tuple((r.desc, r.awaken_num) for r in raw.resonance)


def _chosen_awaken(awaken_all: tuple[str, ...], awaken_effect: list[str]) -> list[str]:
    """异环觉醒可选：按面板 awaken_effect 选中的 EffectN 取 awaken[N-1]，而非顺序前 N 个。"""
    texts: list[str] = []
    for effect in awaken_effect:
        match = re.search(r"\d+", effect)
        if match is None:
            continue
        index = int(match.group()) - 1
        if 0 <= index < len(awaken_all) and awaken_all[index]:
            texts.append(awaken_all[index])
    return texts


def _scan_sentence(
    sentence: str,
    source: str,
    team: list[ParsedBuff],
    self_buffs: list[ParsedBuff],
    enemy: list[EnemyDebuff],
    unparsed: list[str],
    orphans: list[str],
) -> None:
    is_team = _is_team_scope(sentence)
    is_self = not is_team and _SKIP_TOKEN not in sentence and any(t in sentence for t in _SELF_TRIGGERS)
    stats = _extract_stats(sentence)
    matched = False

    for kind, value, element, scope in stats:
        buff = ParsedBuff(kind=kind, value=value, source=source, text=sentence, element=element, scope=scope)
        # 效果文案(套装/武器/觉醒/技能)的增益一律计入：实证都不在脱战面板——面板只含驱动盘词条+角色基础+自身
        # 被动(正则都扫不到)；effect 文案 atk% 的白值反解残差=0、元素增伤面板=0，都证明没进面板。旧版「无触发词=
        # 常驻已在面板」跳过纯属漏算（面板里的来源正则根本看不见，不存在可双计的情形）。条件型按 100% 触发计，
        # 与引擎对所有触发型增益(释放后/暴击后…)一个口径。
        (team if is_team else self_buffs).append(buff)
        matched = True

    for pattern, kind in _ENEMY_RULES:
        found = pattern.search(sentence)
        if found is not None:
            enemy.append(EnemyDebuff(kind=kind, value=_first_num(found) / 100.0, source=source, text=sentence))
            matched = True
            break

    # 无视防御 / 无视抗：恒为装备者自身、不在面板，按自身增益施加（不走触发门控）
    for pattern, kind in _IGNORE_RULES:
        found = pattern.search(sentence)
        if found is not None:
            self_buffs.append(ParsedBuff(kind=kind, value=_first_num(found) / 100.0, source=source, text=sentence))
            matched = True
            break

    # 倍率提升（基础伤害区，装备者自身具名技能/段，恒非面板 → 自身增益、不走触发门控）。
    # scope 存「引号名核心」（去类型前缀），按段名子串匹配；额外伤害段由 segment_mult 的「额外」一致性区分。
    mult = _MULT_RE.search(sentence)
    if mult is not None:
        core = mult.group(1).split("：")[-1].split(":")[-1].strip()
        self_buffs.append(
            ParsedBuff(kind="mult_pct", value=float(mult.group(2)) / 100.0, source=source, text=sentence, scope=core)
        )
        matched = True

    if matched:
        return

    # 解析不出任何增益后才判孤儿：附着/持续/心灵伤害**本体**（无对应倍率段）才 surface；
    # 若句子里「持续/心灵」只是触发条件而真增益已被解析（如安魂曲「每次造成持续伤害时…暴击伤害提高6%」），
    # 上面 matched=True 已 return，不会误吞。
    if is_orphan_damage(sentence):
        orphans.append(f"[{source}] {sentence.strip()}")
        return

    # 仍没解析出的「队友 / 自身条件」句子显式列出，不静默丢弃；伤害描述句（额外伤害 / 造成 N 次 X%攻击力的伤害）不是增益，不列。
    if (
        "%" in sentence
        and (is_team or is_self)
        and any(t in sentence for t in _BUFFY_TOKENS)
        and not _DAMAGE_DESC_RE.search(sentence)
    ):
        unparsed.append(f"[{source}] {sentence.strip()}")


def scan_character_buffs(character: CharacterDetail) -> BuffScan:
    """扫描单角色：全队增益 / 自身条件增益 / 敌人减益。set des2 是自身常驻（已在面板），不重复计。"""
    team: list[ParsedBuff] = []
    self_buffs: list[ParsedBuff] = []
    enemy: list[EnemyDebuff] = []
    unparsed: list[str] = []
    orphans: list[str] = []
    # 觉醒可选：按面板 awaken_effect 选中的 Effect 取对应那条（非顺序前N）；共鸣按 awaken_lev 解锁（觉≥3/觉≥6）。
    awaken_lev = character.awaken_lev  # 共鸣由觉醒等级解锁，非按列表前 N 个切片
    sources: list[tuple[str, str]] = [
        ("套装4件", character.suit.des4),
        ("武器", _resolve_fork_effect(character.fork)),
        *[("觉醒", text) for text in _chosen_awaken(_awaken_texts(character.id), character.awaken_effect)],
        *[("共鸣", desc) for desc, awaken_num in resonance_effects(character.id) if awaken_lev >= awaken_num],
        *[("技能", text) for text in _skill_texts(character.id)],
    ]
    for source, raw_text in sources:
        if not raw_text:
            continue
        for sentence in _SENTENCE_RE.split(_clean(raw_text)):
            stripped = sentence.strip()
            if stripped:
                _scan_sentence(stripped, source, team, self_buffs, enemy, unparsed, orphans)
    return BuffScan(
        owner=character.name,
        team_buffs=tuple(_dedup(team)),
        self_buffs=tuple(_dedup(self_buffs)),
        enemy_debuffs=tuple(_dedup(enemy)),
        unparsed=tuple(dict.fromkeys(unparsed)),
        orphans=tuple(dict.fromkeys(orphans)),
    )


def _dedup(items: Iterable[_T]) -> list[_T]:
    """同 (kind, 值, 文案) 的增益 / 减益只留一份，体现「同名不可叠加」。ParsedBuff 与 EnemyDebuff 通用。"""
    seen: set[tuple[str, float, str]] = set()
    out: list[_T] = []
    for item in items:
        k = (item.kind, round(item.value, 4), item.text)
        if k not in seen:
            seen.add(k)
            out.append(item)
    return out


def bundle_from(buffs: Sequence[ParsedBuff], element: str = "") -> BuffBundle:
    """汇总**全局**增益成 BuffBundle（scope 非空的来源限定增益不计入，避免平摊到所有段=超算）。
    元素限定增伤（buff.element 非空）只在与成员 element 同元素时计入。来源限定增益由
    bundle_for_segment 在逐段结算时按 ability.type/name 单独折算。"""

    def total(kind: str) -> float:
        return sum(
            buff.value
            for buff in buffs
            if buff.kind == kind and not buff.scope and (not buff.element or buff.element == element)
        )

    def ignore(kind: str) -> float:
        # 无视防/无视抗取**最大**而非求和：同效果的「提升至X%」是替换升级非叠加（安魂曲 套装 无视12%
        # +提升至24% 真值=24% 非 36%），且独立来源叠加在真实数据中未见。取 max 保守、修正旧版双计高估。
        values = [buff.value for buff in buffs if buff.kind == kind]
        return max(values) if values else 0.0

    return BuffBundle(
        atk_pct=total("atk_pct"),
        dmg_pct=total("dmg_pct"),
        crit_rate=total("crit_rate"),
        crit_dmg=total("crit_dmg"),
        def_ignore=ignore("def_ignore"),
        res_ignore=ignore("res_ignore"),
    )


def bundle_for_segment(
    buffs: Sequence[ParsedBuff],
    element: str,
    ability_type: str,
    ability_name: str,
    segment_name: str,
) -> BuffBundle:
    """单段的**来源限定**增益增量（只取 scope 非空且命中本段的 buff）。

    只折算 dmg_pct / crit_rate / crit_dmg——真实数据里来源限定增益仅这三类；攻击力% / 无视防御 /
    无视抗恒为全局，已在 bundle_from 计入，这里固定为 0，绝不重复计算。
    """

    def total(kind: str) -> float:
        return sum(
            buff.value
            for buff in buffs
            if buff.kind == kind
            and buff.scope
            and scope_matches(buff.scope, ability_type, ability_name, segment_name)
            and (not buff.element or buff.element == element)
        )

    return BuffBundle(
        dmg_pct=total("dmg_pct"),
        crit_rate=total("crit_rate"),
        crit_dmg=total("crit_dmg"),
    )


def segment_mult(buffs: Sequence[ParsedBuff], segment_name: str) -> float:
    """命中本段的倍率提升合计（基础伤害区，乘到该段倍率上）。

    匹配：buff.scope（引号名核心，如「噩梦」）是段名子串，且「额外」属性一致——`额外伤害倍率提升`
    只进带「额外」的段（如翳「兽牙影刺」额外伤害倍率），普通倍率提升只进不带「额外」的段，互不串扰。
    引号名不在任何段名里的（如浔「浮世来潮」对应段名为「终结伤害倍率」）匹配不到→自然不折，由调用方诚实标注。
    """
    total = 0.0
    for buff in buffs:
        if buff.kind != "mult_pct":
            continue
        # 模式1：引号名核心是段名子串（噩梦/兽牙影刺/致命玫约）。
        core_hit = bool(buff.scope) and buff.scope in segment_name
        # 模式2：具描述性的段名（非裸「伤害倍率」）整体出现在增益文案里（浔「终结伤害倍率」+100%）。
        desc_hit = len(segment_name) > len("伤害倍率") and segment_name in buff.text
        if not (core_hit or desc_hit):
            continue
        # 额外/普通互不串扰；「主动」buff 不漏到「自动」段（九原 主动「致约清算」+50% 不进 自动「致约清算」段）。
        # 用段名前缀 自动「 判定，避免误伤翳「兽牙影刺自动攻击」这种文案里出现的「自动」二字。
        auto_segment = segment_name.startswith("自动")
        if ("额外伤害倍率" in buff.text) == ("额外" in segment_name) and not (auto_segment and "主动" in buff.text):
            total += buff.value
    return total


def enemy_mods(debuffs: Sequence[EnemyDebuff]) -> tuple[float, float]:
    """聚合敌人减防 / 减抗，返回 (减防, 减抗)。减防封顶 0.9 防止防御区失真。"""
    def_reduction = min(0.9, sum(d.value for d in debuffs if d.kind == "def_reduction"))
    res_reduction = sum(d.value for d in debuffs if d.kind == "res_reduction")
    return def_reduction, res_reduction
