from __future__ import annotations

import re

# 增益作用域单一真源。
#
# 增伤区 = 1 + 通用伤害增强 + 伤害类型(元素/心灵)增强 + 伤害来源增强 + 其他 - 造成伤害降低。
# 「伤害来源」即普通攻击 / 变轨技能 / 极轨终结 / 援护技 / 下落攻击 / 极限反击 / Buff / 弧盘 /
# 被动 / 环合 / 无来源——这正是逐技能（per-skill）作用域的分类。来源限定的增伤只加到对应
# 伤害段，不能折进全局增伤区（否则会被平摊到所有段 = 超算）。
#
# 真实数据里命中的限定增益几乎都是「极轨终结：奇零除尽」这种「类型：技能名」引号形式，而对应
# 倍率段名只是「伤害倍率」——所以可靠的绑定落在 ability.type（整条 ultraskill 就是这个技能），
# 而非 segment 段名子串。extract_scope 因此优先把引号里的类型词解析成 type:xxx。

# 来源关键词 → 引擎 ability.type。长词优先（按 key 长度倒序匹配），避免「极轨」「终结」抢在
# 「极轨终结」前命中。
KEYWORD_TO_SCOPE: dict[str, str] = {
    "普通攻击": "type:melee",
    "普攻": "type:melee",
    "变轨技能": "type:skill",
    "极轨终结": "type:ultraskill",
    "极轨": "type:ultraskill",
    "终结": "type:ultraskill",
    "援护技": "type:qte",
    "援护": "type:qte",
}
# type 内细分的段名子串（melee 里的极限反击 / 下落 / 分支）。仅保留语义明确的安全词；真实数据
# 目前没有段级限定增益，此处为前瞻扩展，靠「直接管辖伤害」的强信号触发，不会误吃全局增益。
SEGMENT_KEYWORDS: tuple[str, ...] = ("反击", "下落", "分支")
# 伤害类型标签型增益：DoT / 附着 / 心灵伤害都没有对应倍率段，无法折算，诚实 surface 不入算。
ORPHAN_KEYWORDS: tuple[str, ...] = ("附着物伤害", "附着伤害", "持续伤害", "心灵伤害")
# scope → 展示标签，供卡片/报告呈现作用域。
SCOPE_TO_LABEL: dict[str, str] = {
    "type:melee": "普攻",
    "type:skill": "变轨技能",
    "type:ultraskill": "极轨终结",
    "type:qte": "援护技",
}

# 限定词必须「直接管辖」伤害/暴击短语才算作用域，借此区分「释放『终结』后…」这类触发语
# （增益其实是全局的，引号只是触发条件）。
_DMG_TAIL = r"(?:所?造成的?|的)?(?:[光灵咒暗魂相]属性)?(?:异能)?(?:暴击伤害|暴击率|暴伤|伤害)"
_QUOTE_SCOPE_RE = re.compile(r"[「『]([^」』]+)[」』]" + _DMG_TAIL)
_KW_ALT = "|".join(sorted(KEYWORD_TO_SCOPE, key=len, reverse=True))
_BARE_SCOPE_RE = re.compile(r"(" + _KW_ALT + r")" + _DMG_TAIL)
_SEG_SCOPE_RE = re.compile(r"(" + "|".join(SEGMENT_KEYWORDS) + r")" + _DMG_TAIL)

# 多作用域：「『普攻』和『极限反击』造成伤害+X%」——多个来源由 和/与/或/、 并列、共管同一个伤害短语。
# 一个来源 = 引号名 或 裸来源关键词；并列组须 ≥2 个来源(含连接词)，紧贴 _DMG_TAIL，避免吃到触发语。
_CONNECTOR = r"(?:和|与|、|及|以及|或)"
_SOURCE = r"(?:[「『][^」』]+[」』]|" + _KW_ALT + r")"
_MULTI_SCOPE_RE = re.compile(r"(" + _SOURCE + r"(?:" + _CONNECTOR + _SOURCE + r")+)" + _DMG_TAIL)
_SOURCE_RE = re.compile(r"[「『]([^」』]+)[」』]|(" + _KW_ALT + r")")


def _classify_quote(inner: str) -> str:
    """引号内文案 → scope。含来源类型词取 type:xxx；含段级词(反击/下落/分支)取 segment:；纯技能名降级 ability:<名>。"""
    for keyword in sorted(KEYWORD_TO_SCOPE, key=len, reverse=True):
        if keyword in inner:
            return KEYWORD_TO_SCOPE[keyword]
    for segment in SEGMENT_KEYWORDS:
        if segment in inner:
            return f"segment:{segment}"
    name = inner.split("：")[-1].split(":")[-1].strip()
    return f"ability:{name}" if name else ""


def extract_scope(sentence: str) -> str:
    """识别增益作用域标签。

    返回："" = 全局；单作用域 "type:…"/"ability:…"/"segment:…"；
    多作用域用 "|" 连接（如 "type:skill|type:ultraskill"，scope_matches 命中任一即算）。
    仅当限定词直接管辖伤害/暴击短语时才判定作用域，规避「释放『X』后…」触发语误判为限定。
    """
    multi = _MULTI_SCOPE_RE.search(sentence)
    if multi is not None:
        scopes: list[str] = []
        for quote, bare in _SOURCE_RE.findall(multi.group(1)):
            scope = _classify_quote(quote) if quote else KEYWORD_TO_SCOPE[bare]
            if scope and scope not in scopes:
                scopes.append(scope)
        if len(scopes) >= 2:  # 真并列多作用域；只解析出 1 个则退回单作用域逻辑
            return "|".join(scopes)
    quoted = _QUOTE_SCOPE_RE.search(sentence)
    if quoted is not None:
        return _classify_quote(quoted.group(1))
    bare = _BARE_SCOPE_RE.search(sentence)
    if bare is not None:
        return KEYWORD_TO_SCOPE[bare.group(1)]
    segment = _SEG_SCOPE_RE.search(sentence)
    if segment is not None:
        return f"segment:{segment.group(1)}"
    return ""


def scope_matches(scope: str, ability_type: str, ability_name: str, segment_name: str) -> bool:
    """段级匹配。ability_type / ability_name 来自资源（_AbilityProfile），绝不靠段名反推 type。
    多作用域（"|" 连接）命中任一子作用域即算（如「普攻和极限反击」同时管 melee 段与极限反击段）。"""
    if not scope:
        return True
    if "|" in scope:
        return any(scope_matches(part, ability_type, ability_name, segment_name) for part in scope.split("|"))
    if scope.startswith("type:"):
        return ability_type == scope[len("type:") :]
    if scope.startswith("ability:"):
        return scope[len("ability:") :] in ability_name
    if scope.startswith("segment:"):
        return scope[len("segment:") :] in segment_name
    return False


def is_orphan_damage(sentence: str) -> bool:
    """伤害类型标签型增益（附着/持续/心灵伤害 + 百分比）：无对应倍率段，诚实 surface 不折算。"""
    return "%" in sentence and any(keyword in sentence for keyword in ORPHAN_KEYWORDS)
