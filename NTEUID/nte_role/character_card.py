from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    vw,
    wrap_text,
    add_footer,
    get_nte_bg,
    open_texture,
    rounded_mask,
    clean_rich_text,
    make_nte_role_title,
)
from ..utils.resource.cdn import (
    get_weapon_img,
    get_char_skill_img,
    get_char_awaken_img,
    get_char_detail_img,
    get_char_element_img,
    get_char_property_img,
    get_char_city_skill_img,
    get_char_suit_drive_img,
    get_char_group_black_img,
    get_char_suit_detail_img,
)
from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.sdk.tajiduo_model import (
    CharacterFork,
    CharacterSuit,
    CharacterSkill,
    CharacterDetail,
    CharacterProperty,
    CharacterSuitItem,
)

WIDTH = 1080
PADDING = 36
FOOTER_RESERVE = 80

OUTER_RADIUS = vw(20)
OUTER_PAD_X = vw(15)
OUTER_PAD_Y = vw(26)
SECTION_GAP = vw(20)  # 官方各 section mt-vw-20

# 段头（PN/y5/P5/k5 共用）：图标 w-vw-18 + 中文 text-vw-18 + 副标 text-vw-4 mt-vw-2
SEC_ICON_SIZE = vw(18)
SEC_TITLE_FONT = vw(18)
SEC_SUB_FONT = max(8, vw(7))  # 官方 text-vw-4 太小，下限 8
SEC_TITLE_GAP = vw(2)
SEC_HEADER_GAP_X = vw(2)
SEC_BODY_GAP = vw(5)  # mt-vw-5 between header and inner panel

PORTRAIT_RADIUS = vw(12)
PORTRAIT_IMG_H = vw(226)  # h-vw-226
PORTRAIT_TOP_INSET = vw(6)  # top-vw-6
PORTRAIT_LEFT_INSET = vw(2)  # left-vw-2
PORTRAIT_RIGHT_INSET = vw(2)
NTE_WM_FONT = vw(156)
NTE_WM_OFFSET_X = vw(4)  # -translate-x-4
NTE_WM_OFFSET_Y = vw(1)  # translate-y-1

ELEM_ICON_SIZE = vw(20)  # 元素 + 阵营，官方未给具体宽度，估测
GROUP_ICON_SIZE = vw(20)
NAME_FONT = vw(18)
LV_BADGE_FONT = vw(11)
LV_BADGE_PAD_X = vw(4)
SUB_FONT = max(7, vw(5))  # text-vw-5 太小，下限 7

QUALITY_BLOCK_W = vw(52)  # t5 w-vw-52
QUALITY_LETTER_W = vw(35)  # X4 letter w-vw-35
LIKEABILITY_ICON_W = vw(32)
LIKEABILITY_FONT = vw(15)

AWAKEN_BAND_H = vw(33)
AWAKEN_LEV_FONT = vw(24)
AWAKEN_LABEL_FONT = vw(10)
AWAKEN_DIV_W = vw(1)
AWAKEN_DIV_H = vw(22)
AWAKEN_SLOT_BOX = vw(33)  # h-vw-33
AWAKEN_SLOT_RING = vw(30)  # r5 w-vw-30
AWAKEN_SLOT_INNER = vw(29)  # inner img w-vw-29
AWAKEN_SLOT_LOCK = vw(20)  # nx (effect_lock) — 官方为 w-vw-29 但锁图本身较小，我们按贴图比例

PROP_INNER_RADIUS = vw(8)
PROP_INNER_PAD_X = vw(10)
PROP_INNER_PAD_Y = vw(10)
PROP_ROW_H = vw(30)
PROP_GAP_X = vw(8)
PROP_ICON_SIZE = vw(16)
PROP_NAME_FONT = vw(12)
PROP_VALUE_FONT = vw(12)

SKILL_PANEL_RADIUS = vw(8)
SKILL_PANEL_PAD_X = vw(7)  # px-vw-7
SKILL_PANEL_PAD_Y = vw(10)  # py-vw-10
INNER_HEAD_FONT = vw(13)
INNER_HEAD_GAP = vw(5)  # ml-vw-5
INNER_HEAD_BOTTOM_GAP = vw(11)  # mt-vw-11
INNER_HEAD_ICON = vw(18)
SKILL_CELL_LARGE_W = vw(52)  # 主动
SKILL_CELL_SMALL_W = vw(32)  # 被动 (p5)
SKILL_BG_W = vw(52)  # 主动 bg
SKILL_BG_W_PASSIVE = vw(32)  # 被动 bg
SKILL_ICON_LARGE_W = vw(52)  # 主动 icon overlay
SKILL_ICON_SMALL_W = vw(20)  # 被动 icon overlay
SKILL_GAP_X = vw(6)  # 收紧让 6 个 cell 单行排下；官方 vw-12 但外层 panel 比我们窄
SKILL_NAME_FONT = vw(10)
SKILL_LEV_FONT = vw(8)
SKILL_LEV_PAD_Y = vw(2)
SKILL_NAME_GAP = vw(2)
SKILL_LEV_GAP = vw(2)

# 城技 cell
CITY_CELL_W = vw(52)
CITY_GAP_X = vw(13)
CITY_HEAD_BOTTOM_GAP = vw(12)  # mt-vw-12

# 战斗技能位号文案（依索引映射）— 官方 h5
_BATTLE_SKILL_NAMES = ["普通攻击", "变轨技能", "极轨终结", "援护技", "被动技能", "被动技能"]

FORK_INNER_RADIUS = vw(8)
FORK_INNER_PAD = vw(10)
FORK_ICON_PANEL_W = vw(64)  # ix w-vw-64
FORK_ICON_W = vw(57)  # fork.png w-vw-57
FORK_RIGHT_ML = vw(8)  # ml-vw-8
FORK_GROUP_ICON_W = vw(24)
FORK_NAME_FONT = vw(17)
FORK_NAME_ML = vw(2)
FORK_LV_FONT = vw(12)
FORK_STAR_W = vw(22)  # Z5/X5 w-vw-22
FORK_SLEV_BADGE_W = vw(15)  # bg-#545454 w-vw-15 h-vw-15 rounded-full
FORK_SLEV_FONT = vw(11)
FORK_HZ_FONT = vw(11)
FORK_BUFF_NAME_FONT = vw(12)
FORK_DIVIDER_H = vw(1)
FORK_PROP_CHIP_FONT = vw(12)
FORK_PROP_CHIP_PAD_X = vw(4)
FORK_PROP_CHIP_PAD_Y = vw(5)
FORK_PROP_CHIP_GAP = vw(2)
FORK_PROP_ICON_W = vw(16)
FORK_BUFF_DES_FONT = vw(12)
FORK_DES_FONT = vw(11)
FORK_DES_TOP_GAP = vw(10)
FORK_GAP_Y = vw(7)
FORK_LINE_GAP = vw(4)

SUIT_NAME_FONT = vw(15)
SUIT_NAME_TOP_GAP = vw(12)  # mt-vw-12
SUIT_COND_ICON_W = vw(40)
SUIT_COND_ADD_W = vw(17)
SUIT_COND_TOP_GAP = vw(20)  # mt-vw-20
SUIT_TOP_BOTTOM_GAP = vw(14)  # mt-vw-14 between top and drive grid
DRIVE_CARD_RADIUS = vw(6)
DRIVE_CARD_PAD_Y = vw(6)
DRIVE_CARD_PAD_X = vw(6)
DRIVE_ICON_BG_W = vw(36)  # ix w-vw-36
DRIVE_ICON_W = vw(29)  # drive icon w-vw-29
DRIVE_NAME_FONT = vw(12)
DRIVE_LEV_FONT = vw(10)
DRIVE_LEV_PAD_X = vw(10)
DRIVE_LEV_PAD_Y = vw(2)
DRIVE_INNER_TITLE_FONT = vw(10)
DRIVE_PROP_ICON_W = vw(13)
DRIVE_PROP_NAME_FONT = vw(11)
DRIVE_PROP_VALUE_FONT = vw(11)
DRIVE_PROP_ROW_H = vw(20)
DRIVE_GRID_GAP_X = vw(6)  # gap-x-vw-6
DRIVE_GRID_GAP_Y = vw(6)

COLOR_OUTER = (239, 239, 239, 255)  # #EFEFEF
COLOR_INNER = (220, 220, 220, 255)  # #DCDCDC
COLOR_INNER_LIGHT = (233, 233, 233, 255)  # #E9E9E9
COLOR_NTE_WM_BACK = (47, 47, 47)
COLOR_NTE_WM_FRONT = (39, 39, 39)
COLOR_PORTRAIT_BG = (0, 0, 0, 255)
COLOR_BAND = (0, 0, 0, 178)  # bg-black/70
COLOR_SEC_TITLE = (35, 35, 35)  # #232323
COLOR_SEC_SUB = (177, 177, 177)  # #B1B1B1
COLOR_NAME = COLOR_WHITE
COLOR_LV_BADGE_BG = (207, 187, 144)  # #CFBB90
COLOR_LV_BADGE_TEXT = (49, 49, 49)  # #313131
COLOR_AWAKEN_LEV = (242, 255, 37)  # #F2FF25
COLOR_AWAKEN_LABEL = (206, 219, 0)  # #CEDB00
COLOR_DIVIDER_DARK = (80, 80, 80)
COLOR_BODY_TEXT = (78, 78, 78)  # #4E4E4E
COLOR_BODY_TEXT2 = (84, 84, 84)  # #545454
COLOR_BODY_TEXT3 = (65, 65, 65)  # #414141
COLOR_VALUE_DARK = (35, 35, 35)
COLOR_DES_TEXT = (134, 134, 134)  # #868686
COLOR_PROP_CHIP_BG = (204, 204, 204, 255)  # #CCCCCC
COLOR_DIVIDER_LIGHT = (204, 204, 204)
COLOR_FORK_SLEV = (128, 209, 248)  # #80D1F8
COLOR_FORK_SLEV_BG = (84, 84, 84)
COLOR_FORK_HZ = (50, 180, 242)  # #32B4F2
COLOR_SKILL_LEV_BG = (72, 72, 72)  # #484848
COLOR_BATTLE_MAX = (124, 236, 252)  # #7CECFC
COLOR_CITY_MAX = (255, 89, 149)  # #FF5995
COLOR_PILL_TEXT = (238, 238, 238)  # #EEEEEE
COLOR_DRIVE_LEV_BG = (84, 84, 84)
COLOR_DRIVE_LEV_TEXT = (239, 239, 239)
COLOR_DRIVE_TITLE = (168, 168, 170)  # #A8A8AA
COLOR_DRIVE_VALUE = (35, 35, 35)
COLOR_DRIVE_PROP_BG_ALT = (233, 233, 233, 255)  # #E9E9E9 alternating row

_ZERO = {"0", "0%"}


def _format_value(value: str) -> str:
    """属性数值四舍五入：纯数字（含负号 / 小数）→ 整数；带 `%` 等单位的保留原值。
    例 `15411.5742` → `15411`；`12.2%` 原样。"""
    if not value:
        return value
    raw = value.strip()
    try:
        n = float(raw)
    except ValueError:
        return value
    return str(round(n))


# 官方 buff_des 内嵌标签：<lv>...</> 等级缩放值、<Green2>...</> 计数、<Guang>/<Hun>/<Ling>/<Zhou>/<Xiang>/<An>...</> 元素属性、
# <TextHLT>...</> 强调、<Title>...</> 子小标题、<Italic>...</> 斜体引言、
# <hot textstyle="..." param="...">...</> 跳词条（只取内容文字）。


_RICH_BREAK_RE2 = re.compile(r"(?<![A-Za-z])rn(?![A-Za-z])")
_RICH_TAG_OPEN_RE = re.compile(r"<([A-Za-z][A-Za-z0-9]*)(?:\s[^>]*)?>")
_RICH_TAG_CLOSE_RE = re.compile(r"</[A-Za-z]*>")

_LBD_RE = re.compile(r"\{(\d+)\}")


def _substitute_lbd(text: str, lbd: list[str]) -> str:
    """`<lv>{N}</>` 把 `{N}` 换成 `lbd[N]`；越界保留原文。lbd 为空时直接返回原文。"""
    if not text or not lbd:
        return text

    def _sub(m: re.Match) -> str:
        idx = int(m.group(1))
        return lbd[idx] if 0 <= idx < len(lbd) else m.group(0)

    return _LBD_RE.sub(_sub, text)


_TAG_COLORS = {
    "lv": (50, 180, 242),  # 等级缩放值 — 与 #32B4F2 同色
    "Green2": (95, 200, 150),
    "TextHLT": (242, 255, 37),  # 与觉醒等级同
    "Title": (242, 255, 37),
    # 元素属性高亮：与 CharElement.color 对齐
    "Hun": (180, 110, 220),  # 魂
    "Guang": (245, 190, 80),  # 光
    "Ling": (95, 200, 150),  # 灵
    "Zhou": (110, 145, 220),  # 咒
    "An": (90, 90, 120),  # 暗
    "Xiang": (220, 110, 110),  # 相
}


def _parse_rich_segments(text: str, default_color: tuple[int, int, int]) -> list[tuple[str, tuple[int, int, int]]]:
    """解析 `<Tag>...</>` 嵌套标签为 (片段, 颜色) 列表；未识别的 tag 用 default_color；保留换行。"""
    text = _RICH_BREAK_RE2.sub("\n", text).replace("\\n", "\n")
    segments: list[tuple[str, tuple[int, int, int]]] = []
    color_stack: list[tuple[int, int, int]] = [default_color]
    i = 0
    buf = ""
    while i < len(text):
        m_close = _RICH_TAG_CLOSE_RE.match(text, i)
        m_open = _RICH_TAG_OPEN_RE.match(text, i)
        if m_close:
            if buf:
                segments.append((buf, color_stack[-1]))
                buf = ""
            if len(color_stack) > 1:
                color_stack.pop()
            i = m_close.end()
        elif m_open:
            if buf:
                segments.append((buf, color_stack[-1]))
                buf = ""
            tag = m_open.group(1)
            color_stack.append(_TAG_COLORS.get(tag, color_stack[-1]))
            i = m_open.end()
        else:
            buf += text[i]
            i += 1
    if buf:
        segments.append((buf, color_stack[-1]))
    return segments


def _layout_colored(
    draw: ImageDraw.ImageDraw,
    segments: list[tuple[str, tuple[int, int, int]]],
    font,
    max_w: int,
    max_lines: int | None = None,
) -> list[list[tuple[str, tuple[int, int, int]]]]:
    """把 (text, color) 段按字符宽度折行：每行是 (chunk, color) 列表。"""
    lines: list[list[tuple[str, tuple[int, int, int]]]] = [[]]
    cur_w = 0
    for text, color in segments:
        for char in text:
            if char == "\n":
                lines.append([])
                cur_w = 0
                continue
            ch_w = round(draw.textlength(char, font=font))
            if cur_w + ch_w > max_w and lines[-1]:
                lines.append([])
                cur_w = 0
            if lines[-1] and lines[-1][-1][1] == color:
                lines[-1][-1] = (lines[-1][-1][0] + char, color)
            else:
                lines[-1].append((char, color))
            cur_w += ch_w
        if max_lines and len(lines) > max_lines:
            break
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        if last:
            last[-1] = (last[-1][0].rstrip() + "…", last[-1][1])
    return lines


def _draw_colored_lines(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    lines: list[list[tuple[str, tuple[int, int, int]]]],
    font,
    line_gap: int,
) -> int:
    x, y = xy
    line_h = int(font.size) + line_gap
    for line in lines:
        cx = x
        for chunk, color in line:
            draw.text((cx, y), chunk, font=font, fill=color, anchor="lt")
            cx += round(draw.textlength(chunk, font=font))
        y += line_h
    return len(lines) * line_h


TEXTURE_PATH = Path(__file__).parent / "texture2d" / "character"

# 预加载静态贴图
QUALITY_LETTER_BG = open_texture(TEXTURE_PATH / "quality_letter_bg.png", (QUALITY_BLOCK_W, QUALITY_BLOCK_W))
QUALITY_S_LETTER = open_texture(TEXTURE_PATH / "quality_S_letter.png", (QUALITY_LETTER_W, QUALITY_LETTER_W))
QUALITY_A_LETTER = open_texture(TEXTURE_PATH / "quality_A_letter.png", (QUALITY_LETTER_W, QUALITY_LETTER_W))
LIKEABILITY_ICON = open_texture(TEXTURE_PATH / "likeability_icon.png", (LIKEABILITY_ICON_W, LIKEABILITY_ICON_W))
AWAKEN_RING = open_texture(TEXTURE_PATH / "awaken_band_bg.png", (AWAKEN_SLOT_RING, AWAKEN_SLOT_RING))
AWAKEN_LOCK = open_texture(TEXTURE_PATH / "awaken_slot_lock.png", (AWAKEN_SLOT_LOCK, AWAKEN_SLOT_LOCK))
SKILL_CELL_BG = open_texture(TEXTURE_PATH / "city_skill_cell.png", (SKILL_BG_W, SKILL_BG_W))
SKILL_CELL_BG_PASSIVE = open_texture(TEXTURE_PATH / "city_skill_cell.png", (SKILL_BG_W_PASSIVE, SKILL_BG_W_PASSIVE))
CITY_CELL_BG = open_texture(TEXTURE_PATH / "city_skill_cell.png", (CITY_CELL_W, CITY_CELL_W))
SUIT_TOP_BG = open_texture(TEXTURE_PATH / "suit_top_bg.png")
DRIVE_CELL_BG_FORK = open_texture(TEXTURE_PATH / "drive_cell_bg.png", (FORK_ICON_PANEL_W, FORK_ICON_PANEL_W))
DRIVE_CELL_BG_DRIVE = open_texture(TEXTURE_PATH / "drive_cell_bg.png", (DRIVE_ICON_BG_W, DRIVE_ICON_BG_W))
DRIVE_STAR = open_texture(TEXTURE_PATH / "drive_star.png", (FORK_STAR_W, FORK_STAR_W))
DRIVE_STAR_NONE = open_texture(TEXTURE_PATH / "drive_star_none.png", (FORK_STAR_W, FORK_STAR_W))
SECTION_PROPS_ICON = open_texture(TEXTURE_PATH / "section_props_icon.png", (SEC_ICON_SIZE, SEC_ICON_SIZE))
SECTION_SKILL_ICON = open_texture(TEXTURE_PATH / "char_skill_attr.png", (SEC_ICON_SIZE, SEC_ICON_SIZE))
SECTION_ATTR_ICON = open_texture(TEXTURE_PATH / "char_section_attr.png", (SEC_ICON_SIZE, SEC_ICON_SIZE))
INNER_BATTLE_ICON = open_texture(TEXTURE_PATH / "section_battle_skill_icon.png", (INNER_HEAD_ICON, INNER_HEAD_ICON))
INNER_CITY_ICON = open_texture(TEXTURE_PATH / "char_city_section.png", (INNER_HEAD_ICON, INNER_HEAD_ICON))
SUIT_COND_ADD = open_texture(TEXTURE_PATH / "suit_condition_add_icon.png", (SUIT_COND_ADD_W, SUIT_COND_ADD_W))


sec_title_font = nte_font_origin(SEC_TITLE_FONT)
sec_sub_font = nte_font_origin(SEC_SUB_FONT)
inner_head_font = nte_font_origin(INNER_HEAD_FONT)
name_font = nte_font_origin(NAME_FONT)
lv_badge_font = nte_font_origin(LV_BADGE_FONT)
sub_font = nte_font_origin(SUB_FONT)
likeability_font = nte_font_origin(LIKEABILITY_FONT)
nte_wm_font = nte_font_origin(NTE_WM_FONT)
awaken_lev_font = nte_font_origin(AWAKEN_LEV_FONT)
awaken_label_font = nte_font_origin(AWAKEN_LABEL_FONT)
prop_name_font = nte_font_origin(PROP_NAME_FONT)
prop_value_font = nte_font_origin(PROP_VALUE_FONT)
skill_name_font = nte_font_origin(SKILL_NAME_FONT)
skill_lev_font = nte_font_origin(SKILL_LEV_FONT)
fork_name_font = nte_font_origin(FORK_NAME_FONT)
fork_lv_font = nte_font_origin(FORK_LV_FONT)
fork_slev_font = nte_font_origin(FORK_SLEV_FONT)
fork_hz_font = nte_font_origin(FORK_HZ_FONT)
fork_buff_name_font = nte_font_origin(FORK_BUFF_NAME_FONT)
fork_buff_des_font = nte_font_origin(FORK_BUFF_DES_FONT)
fork_des_font = nte_font_origin(FORK_DES_FONT)
fork_chip_font = nte_font_origin(FORK_PROP_CHIP_FONT)
suit_name_font = nte_font_origin(SUIT_NAME_FONT)
drive_name_font = nte_font_origin(DRIVE_NAME_FONT)
drive_lev_font = nte_font_origin(DRIVE_LEV_FONT)
drive_title_font = nte_font_origin(DRIVE_INNER_TITLE_FONT)
drive_prop_name_font = nte_font_origin(DRIVE_PROP_NAME_FONT)
drive_prop_value_font = nte_font_origin(DRIVE_PROP_VALUE_FONT)


def _resize(img: Image.Image | None, size: int) -> Image.Image | None:
    if img is None:
        return None
    return img.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    suffix = "…"
    s = text
    while s and draw.textlength(s + suffix, font=font) > max_w:
        s = s[:-1]
    return s + suffix


def _filter_props(props: list[CharacterProperty]) -> list[CharacterProperty]:
    return [p for p in props if p.name and p.value not in _ZERO]


def _section_header_h() -> int:
    return max(SEC_ICON_SIZE, int(sec_title_font.size) + SEC_TITLE_GAP + int(sec_sub_font.size))


def _draw_section_header(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], icon: Image.Image, title_zh: str
) -> int:
    """官方 PN/y5/P5/k5 段头：图标 w-vw-18 + 中文 + "CHARACTER ATTRIBUTE" 副标。"""
    x, y = xy
    canvas.alpha_composite(icon, (x, y))
    text_x = x + SEC_ICON_SIZE + SEC_HEADER_GAP_X
    draw.text((text_x, y), title_zh, font=sec_title_font, fill=COLOR_SEC_TITLE, anchor="lt")
    draw.text(
        (text_x, y + int(sec_title_font.size) + SEC_TITLE_GAP),
        "CHARACTER ATTRIBUTE",
        font=sec_sub_font,
        fill=COLOR_SEC_SUB,
        anchor="lt",
    )
    return _section_header_h()


def _draw_inner_header(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], icon: Image.Image, title: str
) -> int:
    x, y = xy
    canvas.alpha_composite(icon, (x, y))
    draw.text(
        (x + INNER_HEAD_ICON + INNER_HEAD_GAP, y + INNER_HEAD_ICON // 2),
        title,
        font=inner_head_font,
        fill=COLOR_BODY_TEXT,
        anchor="lm",
    )
    return INNER_HEAD_ICON


def _make_nte_watermark(panel_w: int, panel_h: int) -> Image.Image:
    """两层旋转 NTE 水印：里层 #2f2f2f 偏移、外层 #272727 重叠。整体 -rotate-15。"""
    layer = Image.new("RGBA", (panel_w * 2, panel_h * 2), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    cx, cy = layer.width // 2, layer.height // 2
    d.text((cx - NTE_WM_OFFSET_X, cy + NTE_WM_OFFSET_Y), "NTE", font=nte_wm_font, fill=COLOR_NTE_WM_BACK, anchor="mm")
    d.text((cx, cy), "NTE", font=nte_wm_font, fill=COLOR_NTE_WM_FRONT, anchor="mm")
    rotated = layer.rotate(15, resample=Image.Resampling.BICUBIC)
    crop_x = (rotated.width - panel_w) // 2
    crop_y = (rotated.height - panel_h) // 2
    return rotated.crop((crop_x, crop_y, crop_x + panel_w, crop_y + panel_h))


def _quality_letter(quality_value: str) -> Image.Image | None:
    """官方 X4 只映射 ORANGE→S 字图、PURPLE→A 字图；其他品质无图（返回 None 由占位绘）。"""
    return {
        "ITEM_QUALITY_ORANGE": QUALITY_S_LETTER,
        "ITEM_QUALITY_PURPLE": QUALITY_A_LETTER,
    }.get(quality_value)


async def _draw_portrait(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, character: CharacterDetail
) -> int:
    """nC：黑底 rounded-vw-12，NTE 水印 + 半身像 + 顶部左/右浮层 + 底部黑带觉醒。"""
    x, y = xy
    panel_w = width
    panel_h = PORTRAIT_IMG_H
    layer = Image.new("RGBA", (panel_w, panel_h), COLOR_PORTRAIT_BG)

    # NTE 水印
    layer.alpha_composite(_make_nte_watermark(panel_w, panel_h), (0, 0))

    # 半身像 h-vw-226 w-full
    art = await get_char_detail_img(character.id)
    if art is not None:
        art = art.convert("RGBA")
        ratio = panel_w / art.width
        new_h = round(art.height * ratio)
        scaled = art.resize((panel_w, new_h), Image.Resampling.LANCZOS)
        crop_top = max(0, (new_h - panel_h) // 2)
        layer.alpha_composite(scaled.crop((0, crop_top, panel_w, crop_top + panel_h)), (0, 0))

    # 底部黑带（h-vw-33 absolute bottom-0 bg-black/70）
    band = Image.new("RGBA", (panel_w, AWAKEN_BAND_H), COLOR_BAND)
    layer.alpha_composite(band, (0, panel_h - AWAKEN_BAND_H))

    canvas.paste(layer, (x, y), rounded_mask((panel_w, panel_h), PORTRAIT_RADIUS))

    # ---- 左上块 ----
    left_x = x + PORTRAIT_LEFT_INSET
    top_y = y + PORTRAIT_TOP_INSET
    elem_img = _resize(await get_char_element_img(character.element_type.value), ELEM_ICON_SIZE)
    group_img = _resize(await get_char_group_black_img(character.group_type.value), GROUP_ICON_SIZE)
    icon_col_w = max(ELEM_ICON_SIZE, GROUP_ICON_SIZE)
    if elem_img is not None:
        canvas.alpha_composite(elem_img, (left_x + (icon_col_w - ELEM_ICON_SIZE) // 2, top_y))
    if group_img is not None:
        canvas.alpha_composite(
            group_img,
            (left_x + (icon_col_w - GROUP_ICON_SIZE) // 2, top_y + ELEM_ICON_SIZE + vw(5)),
        )
    text_block_x = left_x + icon_col_w + vw(2)  # ml-vw-2
    name_y = top_y + vw(5)  # mt-vw-5
    draw.text((text_block_x, name_y), character.name, font=name_font, fill=COLOR_NAME, anchor="lt")
    name_w = round(draw.textlength(character.name, font=name_font))
    lv_text = f"Lv:{character.alev}"
    lv_w = round(draw.textlength(lv_text, font=lv_badge_font)) + LV_BADGE_PAD_X * 2
    lv_h = int(lv_badge_font.size) + vw(4)
    lv_x = text_block_x + name_w + vw(7)
    lv_y = name_y + (int(name_font.size) - lv_h) // 2
    badge = Image.new("RGBA", (lv_w, lv_h), COLOR_LV_BADGE_BG)
    canvas.paste(badge, (lv_x, lv_y), rounded_mask((lv_w, lv_h), vw(2)))
    draw.text((lv_x + lv_w // 2, lv_y + lv_h // 2), lv_text, font=lv_badge_font, fill=COLOR_LV_BADGE_TEXT, anchor="mm")
    sub_y = name_y + int(name_font.size) + vw(2)
    draw.text((text_block_x, sub_y), "MY  CHARACTER", font=sub_font, fill=(177, 177, 177), anchor="lt")

    # ---- 右上块 ----
    q_x = x + panel_w - PORTRAIT_RIGHT_INSET - QUALITY_BLOCK_W
    q_y = y + PORTRAIT_TOP_INSET
    canvas.alpha_composite(QUALITY_LETTER_BG, (q_x, q_y))
    letter = _quality_letter(character.quality.value)
    if letter is not None:
        canvas.alpha_composite(
            letter,
            (q_x + (QUALITY_BLOCK_W - QUALITY_LETTER_W) // 2, q_y + (QUALITY_BLOCK_W - QUALITY_LETTER_W) // 2),
        )
    else:
        # B/C/N 品质官方没图，绘制白色字母占位
        draw.text(
            (q_x + QUALITY_BLOCK_W // 2, q_y + QUALITY_BLOCK_W // 2),
            character.quality.label,
            font=name_font,
            fill=COLOR_WHITE,
            anchor="mm",
        )
    like_y = q_y + QUALITY_BLOCK_W + vw(3)  # mt-vw-3
    canvas.alpha_composite(LIKEABILITY_ICON, (q_x + (QUALITY_BLOCK_W - LIKEABILITY_ICON_W) // 2, like_y))
    draw.text(
        (q_x + QUALITY_BLOCK_W // 2, like_y + LIKEABILITY_ICON_W // 2),
        str(character.likeability_lev),
        font=likeability_font,
        fill=COLOR_WHITE,
        anchor="mm",
    )

    # ---- 觉醒底带 ----
    band_y = y + panel_h - AWAKEN_BAND_H
    band_inner_x = x + vw(15)  # px-vw-17 左侧内距，估测
    band_cy = band_y + AWAKEN_BAND_H // 2
    draw.text(
        (band_inner_x, band_cy),
        str(character.awaken_lev),
        font=awaken_lev_font,
        fill=COLOR_AWAKEN_LEV,
        anchor="lm",
    )
    awk_w = round(draw.textlength(str(character.awaken_lev), font=awaken_lev_font))
    label_x = band_inner_x + awk_w + vw(2)
    draw.text((label_x, band_cy), "觉醒等级", font=awaken_label_font, fill=COLOR_AWAKEN_LABEL, anchor="lm")
    label_w = round(draw.textlength("觉醒等级", font=awaken_label_font))
    div_x = label_x + label_w + vw(8)
    draw.line(
        [(div_x, band_cy - AWAKEN_DIV_H // 2), (div_x, band_cy + AWAKEN_DIV_H // 2)],
        fill=COLOR_DIVIDER_DARK,
        width=AWAKEN_DIV_W,
    )

    # 6 槽
    slots_x_start = div_x + vw(8)
    awaken_n = max(0, min(6, character.awaken_lev))
    for slot in range(6):
        sx = slots_x_start + slot * AWAKEN_SLOT_BOX
        sy = band_cy - AWAKEN_SLOT_BOX // 2
        # ring 框
        ring_x = sx + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_RING) // 2
        ring_y = sy + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_RING) // 2
        canvas.alpha_composite(AWAKEN_RING, (ring_x, ring_y))
        # inner: 解锁 → effect 图，未解锁 → 锁
        if slot < awaken_n and slot < len(character.awaken_effect):
            effect_img = _resize(
                await get_char_awaken_img(character.id, character.awaken_effect[slot]),
                AWAKEN_SLOT_INNER,
            )
            if effect_img is not None:
                canvas.alpha_composite(
                    effect_img,
                    (sx + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_INNER) // 2, sy + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_INNER) // 2),
                )
        else:
            canvas.alpha_composite(
                AWAKEN_LOCK,
                (sx + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_LOCK) // 2, sy + (AWAKEN_SLOT_BOX - AWAKEN_SLOT_LOCK) // 2),
            )

    return panel_h


def _props_panel_h(props: list[CharacterProperty]) -> int:
    if not props:
        return 0
    rows_per_col = 3
    panel_body_h = rows_per_col * PROP_ROW_H
    return PROP_INNER_PAD_Y * 2 + panel_body_h


async def _draw_props(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, properties: list[CharacterProperty]
) -> int:
    visible = _filter_props(properties)[:6]  # 官方 slice(0,6)
    head_h = _draw_section_header(canvas, draw, xy, SECTION_PROPS_ICON, "角色属性")
    if not visible:
        return head_h
    panel_x, panel_y = xy[0], xy[1] + head_h + SEC_BODY_GAP
    panel_h = _props_panel_h(visible)
    bg = Image.new("RGBA", (width, panel_h), COLOR_INNER)
    canvas.paste(bg, (panel_x, panel_y), rounded_mask((width, panel_h), PROP_INNER_RADIUS))

    # 2 列 × 3 行；col0=props[0:3], col1=props[3:6]
    col_w = (width - PROP_INNER_PAD_X * 2 - PROP_GAP_X) // 2
    icons = [await get_char_property_img(p.id) for p in visible]
    for idx, (prop, icon) in enumerate(zip(visible, icons)):
        col = idx // 3
        row = idx % 3
        cx = panel_x + PROP_INNER_PAD_X + col * (col_w + PROP_GAP_X)
        cy = panel_y + PROP_INNER_PAD_Y + row * PROP_ROW_H
        # 单元格用 #D9D9D9 rounded
        cell_bg = Image.new("RGBA", (col_w, PROP_ROW_H - vw(4)), (217, 217, 217, 255))
        canvas.paste(cell_bg, (cx, cy + vw(2)), rounded_mask((col_w, PROP_ROW_H - vw(4)), vw(8)))
        icon_img = _resize(icon, PROP_ICON_SIZE)
        if icon_img is not None:
            canvas.alpha_composite(icon_img, (cx + vw(8), cy + (PROP_ROW_H - PROP_ICON_SIZE) // 2))
        text_x = cx + vw(8) + PROP_ICON_SIZE + vw(4)
        max_w = col_w - (text_x - cx) - vw(60)
        draw.text(
            (text_x, cy + PROP_ROW_H // 2),
            _truncate(draw, prop.name, prop_name_font, max_w),
            font=prop_name_font,
            fill=COLOR_BODY_TEXT3,
            anchor="lm",
        )
        draw.text(
            (cx + col_w - vw(8), cy + PROP_ROW_H // 2),
            _format_value(prop.value),
            font=prop_value_font,
            fill=COLOR_BODY_TEXT3,
            anchor="rm",
        )

    # 「详细属性 →」入口暂不渲染（pillow 静态卡无法做点击展开）

    return head_h + SEC_BODY_GAP + panel_h


def _battle_skill_cell_h() -> int:
    """主动技能 cell 高度：bg + name + lev pill；被动同高，仅 bg/icon 较小。"""
    return (
        SKILL_BG_W
        + SKILL_NAME_GAP
        + int(skill_name_font.size)
        + SKILL_LEV_GAP
        + int(skill_lev_font.size)
        + SKILL_LEV_PAD_Y * 2
    )


async def _draw_battle_skill_cell(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    skill: CharacterSkill,
    label: str,
    cell_w: int,
    bg_w: int,
    icon_w: int,
) -> None:
    x, y = xy
    bg_y_offset = 0
    bg_x = x + (cell_w - bg_w) // 2
    canvas.alpha_composite(SKILL_CELL_BG if bg_w == SKILL_BG_W else SKILL_CELL_BG_PASSIVE, (bg_x, y + bg_y_offset))
    icon = _resize(await get_char_skill_img(skill.id), icon_w) if skill.id else None
    if icon is not None:
        canvas.alpha_composite(icon, (x + (cell_w - icon_w) // 2, y + bg_y_offset + (bg_w - icon_w) // 2))
    name_y = y + bg_w + SKILL_NAME_GAP
    draw.text(
        (x + cell_w // 2, name_y),
        _truncate(draw, label, skill_name_font, cell_w),
        font=skill_name_font,
        fill=COLOR_BODY_TEXT,
        anchor="mt",
    )
    pill_y = name_y + int(skill_name_font.size) + SKILL_LEV_GAP
    pill_h = int(skill_lev_font.size) + SKILL_LEV_PAD_Y * 2
    pill_bg = Image.new("RGBA", (cell_w, pill_h), COLOR_SKILL_LEV_BG)
    canvas.paste(pill_bg, (x, pill_y), rounded_mask((cell_w, pill_h), vw(5)))
    is_max = skill.level == 10  # 普通主动 & 被动 max=10
    pill_text = "MAX" if is_max else f"{skill.level}/{10}"
    draw.text(
        (x + cell_w // 2, pill_y + pill_h // 2),
        pill_text,
        font=skill_lev_font,
        fill=COLOR_BATTLE_MAX if is_max else COLOR_PILL_TEXT,
        anchor="mm",
    )


async def _draw_battle_skills_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    skills: list[CharacterSkill],
) -> int:
    """g5：bg-#DCDCDC rounded px-vw-7 py-vw-10 内嵌 战斗技能 头 + 单元格 flex-wrap。"""
    x, y = xy
    head_h = INNER_HEAD_ICON
    cell_h = _battle_skill_cell_h()
    # 排版：active 用 SKILL_CELL_LARGE_W 列宽，passive 用 SKILL_CELL_SMALL_W 列宽
    used_w = SKILL_PANEL_PAD_X
    rows: list[list[tuple[CharacterSkill, str, int, int, int]]] = [[]]
    for idx, skill in enumerate(skills):
        is_passive = skill.type == "Passive"
        cell_w = SKILL_CELL_SMALL_W if is_passive else SKILL_CELL_LARGE_W
        bg_w = SKILL_BG_W_PASSIVE if is_passive else SKILL_BG_W
        icon_w = SKILL_ICON_SMALL_W if is_passive else SKILL_ICON_LARGE_W
        label = _BATTLE_SKILL_NAMES[idx] if idx < len(_BATTLE_SKILL_NAMES) else (skill.name or "技能")
        next_w = used_w + cell_w + (SKILL_GAP_X if rows[-1] else 0)
        if next_w > width - SKILL_PANEL_PAD_X:
            rows.append([])
            used_w = SKILL_PANEL_PAD_X
            next_w = used_w + cell_w
        rows[-1].append((skill, label, cell_w, bg_w, icon_w))
        used_w = next_w

    grid_h = len(rows) * cell_h + max(0, len(rows) - 1) * SKILL_GAP_X
    panel_h = SKILL_PANEL_PAD_Y * 2 + head_h + INNER_HEAD_BOTTOM_GAP + grid_h

    bg = Image.new("RGBA", (width, panel_h), COLOR_INNER)
    canvas.paste(bg, (x, y), rounded_mask((width, panel_h), SKILL_PANEL_RADIUS))
    _draw_inner_header(canvas, draw, (x + SKILL_PANEL_PAD_X, y + SKILL_PANEL_PAD_Y), INNER_BATTLE_ICON, "战斗技能")

    cy = y + SKILL_PANEL_PAD_Y + head_h + INNER_HEAD_BOTTOM_GAP
    for row in rows:
        row_w = sum(c[2] for c in row) + SKILL_GAP_X * (len(row) - 1)
        cx = x + (width - row_w) // 2
        for skill, label, cell_w, bg_w, icon_w in row:
            await _draw_battle_skill_cell(canvas, draw, (cx, cy), skill, label, cell_w, bg_w, icon_w)
            cx += cell_w + SKILL_GAP_X
        cy += cell_h + SKILL_GAP_X

    return panel_h


async def _draw_city_skills_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    skills: list[CharacterSkill],
) -> int:
    """u5：bg-#DCDCDC rounded px-vw-7 py-vw-10 + 生活技能 头 + cells flex-row gap-x-vw-13。"""
    x, y = xy
    head_h = INNER_HEAD_ICON
    cell_h = _battle_skill_cell_h()
    panel_h = SKILL_PANEL_PAD_Y * 2 + head_h + CITY_HEAD_BOTTOM_GAP + cell_h
    bg = Image.new("RGBA", (width, panel_h), COLOR_INNER)
    canvas.paste(bg, (x, y), rounded_mask((width, panel_h), SKILL_PANEL_RADIUS))
    _draw_inner_header(canvas, draw, (x + SKILL_PANEL_PAD_X, y + SKILL_PANEL_PAD_Y), INNER_CITY_ICON, "生活技能")

    cells_w = len(skills) * CITY_CELL_W + max(0, len(skills) - 1) * CITY_GAP_X
    start_x = x + (width - cells_w) // 2
    cy = y + SKILL_PANEL_PAD_Y + head_h + CITY_HEAD_BOTTOM_GAP
    for skill in skills:
        canvas.alpha_composite(CITY_CELL_BG, (start_x, cy))
        if skill.id:
            icon = _resize(await get_char_city_skill_img(skill.id), CITY_CELL_W)
            if icon is not None:
                canvas.alpha_composite(icon, (start_x, cy))
        name_y = cy + CITY_CELL_W + SKILL_NAME_GAP
        draw.text(
            (start_x + CITY_CELL_W // 2, name_y),
            _truncate(draw, skill.name, skill_name_font, CITY_CELL_W),
            font=skill_name_font,
            fill=COLOR_BODY_TEXT,
            anchor="mt",
        )
        pill_y = name_y + int(skill_name_font.size) + SKILL_LEV_GAP
        pill_h = int(skill_lev_font.size) + SKILL_LEV_PAD_Y * 2
        pill_bg = Image.new("RGBA", (CITY_CELL_W, pill_h), COLOR_SKILL_LEV_BG)
        canvas.paste(pill_bg, (start_x, pill_y), rounded_mask((CITY_CELL_W, pill_h), vw(5)))
        # 城技 total 默认 5
        total = 5
        is_max = skill.level >= total
        pill_text = "MAX" if is_max else f"{skill.level}/{total}"
        draw.text(
            (start_x + CITY_CELL_W // 2, pill_y + pill_h // 2),
            pill_text,
            font=skill_lev_font,
            fill=COLOR_CITY_MAX if is_max else COLOR_PILL_TEXT,
            anchor="mm",
        )
        start_x += CITY_CELL_W + CITY_GAP_X
    return panel_h


async def _draw_skills(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    character: CharacterDetail,
) -> int:
    """y5：段头 角色异能 + 战斗技能 panel + 生活技能 panel。"""
    head_h = _draw_section_header(canvas, draw, xy, SECTION_SKILL_ICON, "角色异能")
    cursor = xy[1] + head_h + SEC_BODY_GAP
    skills = [s for s in character.skills if s.name]
    city = [s for s in character.city_skills if s.name]
    if skills:
        panel_h = await _draw_battle_skills_panel(canvas, draw, (xy[0], cursor), width, skills)
        cursor += panel_h + SEC_BODY_GAP
    if city:
        panel_h = await _draw_city_skills_panel(canvas, draw, (xy[0], cursor), width, city)
        cursor += panel_h
    return cursor - xy[1]


FORK_BUFF_MAX_LINES = 8


def _fork_panel_h(draw: ImageDraw.ImageDraw, fork: CharacterFork, width: int) -> int:
    if not fork.id:
        return 0
    inner_w = width - FORK_INNER_PAD * 2
    info_h = max(
        FORK_ICON_PANEL_W,
        int(fork_name_font.size) + FORK_LINE_GAP + int(fork_lv_font.size) + FORK_LINE_GAP + FORK_STAR_W,
    )
    slev_row_h = max(FORK_SLEV_BADGE_W, int(fork_buff_name_font.size))
    chips = fork.properties
    chip_h = FORK_PROP_ICON_W + FORK_PROP_CHIP_PAD_Y * 2 if chips else 0
    buff_h = 0
    if fork.buff_des:
        # 与 draw 走同一管线：lbd 替换 → 富文本分段 → 同 max_lines 折行
        substituted = _substitute_lbd(fork.buff_des, fork.lbd)
        segments = _parse_rich_segments(substituted, COLOR_BODY_TEXT2)
        lines = _layout_colored(draw, segments, fork_buff_des_font, inner_w, max_lines=FORK_BUFF_MAX_LINES)
        buff_h = len(lines) * (int(fork_buff_des_font.size) + FORK_LINE_GAP)
    des_h = 0
    if fork.des:
        d_lines = wrap_text(draw, clean_rich_text(fork.des), fork_des_font, inner_w, max_lines=2)
        des_h = FORK_DES_TOP_GAP + len(d_lines) * (int(fork_des_font.size) + FORK_LINE_GAP)
    return (
        FORK_INNER_PAD * 2
        + info_h
        + vw(7)
        + slev_row_h
        + vw(2)
        + (chip_h + vw(2) if chip_h else 0)
        + (buff_h + vw(8) if buff_h else 0)
        + des_h
    )


async def _draw_fork_chip(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    prop: CharacterProperty,
) -> int:
    """K5：bg-#CCCCCC rounded， icon + name + +value。"""
    x, y = xy
    icon = _resize(await get_char_property_img(prop.id), FORK_PROP_ICON_W)
    name = prop.name
    value = f"+{_format_value(prop.value)}"
    pad = FORK_PROP_CHIP_PAD_X
    name_w = round(draw.textlength(name, font=fork_chip_font))
    value_w = round(draw.textlength(value, font=fork_chip_font))
    chip_w = pad * 2 + FORK_PROP_ICON_W + vw(4) + name_w + vw(8) + value_w
    chip_h = FORK_PROP_ICON_W + FORK_PROP_CHIP_PAD_Y * 2
    bg = Image.new("RGBA", (chip_w, chip_h), COLOR_PROP_CHIP_BG)
    canvas.paste(bg, (x, y), rounded_mask((chip_w, chip_h), vw(4)))
    cx = x + pad
    cy = y + chip_h // 2
    if icon is not None:
        canvas.alpha_composite(icon, (cx, y + (chip_h - FORK_PROP_ICON_W) // 2))
    cx += FORK_PROP_ICON_W + vw(4)
    draw.text((cx, cy), name, font=fork_chip_font, fill=COLOR_BODY_TEXT2, anchor="lm")
    cx += name_w + vw(8)
    draw.text((cx, cy), value, font=fork_chip_font, fill=COLOR_VALUE_DARK, anchor="lm")
    return chip_w


async def _draw_fork(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, fork: CharacterFork
) -> int:
    if not fork.id:
        return 0
    head_h = _draw_section_header(canvas, draw, xy, SECTION_ATTR_ICON, "弧盘")
    panel_y = xy[1] + head_h + SEC_BODY_GAP
    panel_x = xy[0]
    panel_w = width
    panel_h = _fork_panel_h(draw, fork, panel_w)

    bg = Image.new("RGBA", (panel_w, panel_h), COLOR_INNER)
    canvas.paste(bg, (panel_x, panel_y), rounded_mask((panel_w, panel_h), FORK_INNER_RADIUS))

    body_x = panel_x + FORK_INNER_PAD
    body_y = panel_y + FORK_INNER_PAD

    # I5: 左 icon panel + 右 name/lv/stars
    canvas.alpha_composite(DRIVE_CELL_BG_FORK, (body_x, body_y))
    fork_img = _resize(await get_weapon_img(fork.id), FORK_ICON_W) if fork.id else None
    if fork_img is not None:
        canvas.alpha_composite(
            fork_img,
            (body_x + (FORK_ICON_PANEL_W - FORK_ICON_W) // 2, body_y + (FORK_ICON_PANEL_W - FORK_ICON_W) // 2),
        )
    right_x = body_x + FORK_ICON_PANEL_W + FORK_RIGHT_ML
    right_y = body_y
    group_img = (
        _resize(await get_char_group_black_img(fork.group_type.value), FORK_GROUP_ICON_W) if fork.group_type else None
    )
    if group_img is not None:
        canvas.alpha_composite(group_img, (right_x, right_y + vw(2)))
    name_x = right_x + (FORK_GROUP_ICON_W if group_img is not None else 0) + FORK_NAME_ML
    draw.text((name_x, right_y + vw(2)), fork.name, font=fork_name_font, fill=COLOR_BODY_TEXT, anchor="lt")
    lv_y = right_y + max(FORK_GROUP_ICON_W, int(fork_name_font.size)) + vw(4)
    draw.text(
        (right_x, lv_y),
        f"Lv.{fork.alev}",
        font=fork_lv_font,
        fill=COLOR_BODY_TEXT,
        anchor="lt",
    )
    stars_y = lv_y + int(fork_lv_font.size) + vw(4)
    blev = int(fork.blev) if str(fork.blev).isdigit() else 0
    for i in range(6):
        star = DRIVE_STAR if i < blev else DRIVE_STAR_NONE
        canvas.alpha_composite(star, (right_x + i * (FORK_STAR_W + vw(2)), stars_y))

    info_h_max = max(FORK_ICON_PANEL_W, stars_y + FORK_STAR_W - body_y)
    cursor_y = body_y + info_h_max + FORK_GAP_Y

    # slev 圆徽 + 「混频X阶」 + buffName + 横线
    slev_str = fork.slev
    badge = Image.new("RGBA", (FORK_SLEV_BADGE_W, FORK_SLEV_BADGE_W), (0, 0, 0, 0))
    bd = ImageDraw.Draw(badge)
    bd.ellipse((0, 0, FORK_SLEV_BADGE_W - 1, FORK_SLEV_BADGE_W - 1), fill=COLOR_FORK_SLEV_BG)
    bd.text(
        (FORK_SLEV_BADGE_W // 2, FORK_SLEV_BADGE_W // 2),
        slev_str,
        font=fork_slev_font,
        fill=COLOR_FORK_SLEV,
        anchor="mm",
    )
    canvas.alpha_composite(badge, (body_x, cursor_y))
    hz_x = body_x + FORK_SLEV_BADGE_W + vw(4)
    hz_text = f"混频{slev_str}阶"
    draw.text((hz_x, cursor_y + FORK_SLEV_BADGE_W // 2), hz_text, font=fork_hz_font, fill=COLOR_FORK_HZ, anchor="lm")
    hz_w = round(draw.textlength(hz_text, font=fork_hz_font))
    buff_name_x = hz_x + hz_w + vw(8)
    if fork.buff_name:
        draw.text(
            (buff_name_x, cursor_y + FORK_SLEV_BADGE_W // 2),
            fork.buff_name,
            font=fork_buff_name_font,
            fill=COLOR_BODY_TEXT,
            anchor="lm",
        )
    # 横线占满剩余宽度
    line_y = cursor_y + FORK_SLEV_BADGE_W + vw(2)
    draw.line(
        [(body_x, line_y), (panel_x + panel_w - FORK_INNER_PAD, line_y)],
        fill=COLOR_DIVIDER_LIGHT,
        width=FORK_DIVIDER_H,
    )
    cursor_y = line_y + vw(4)

    # 属性 chips（K5 行：gap-x-vw-2）
    if fork.properties:
        chip_x = body_x
        for prop in fork.properties:
            w_used = await _draw_fork_chip(canvas, draw, (chip_x, cursor_y), prop)
            chip_x += w_used + FORK_PROP_CHIP_GAP
        cursor_y += FORK_PROP_ICON_W + FORK_PROP_CHIP_PAD_Y * 2 + vw(2)

    # buffDes：彩色分段（<lv>/<Green2>/元素 tag 等独立着色）+ lbd 参数替换
    if fork.buff_des:
        cursor_y += vw(8)
        raw = _substitute_lbd(fork.buff_des, fork.lbd)
        segments = _parse_rich_segments(raw, COLOR_BODY_TEXT2)
        lines = _layout_colored(
            draw, segments, fork_buff_des_font, panel_w - FORK_INNER_PAD * 2, max_lines=FORK_BUFF_MAX_LINES
        )
        cursor_y += _draw_colored_lines(draw, (body_x, cursor_y), lines, fork_buff_des_font, FORK_LINE_GAP)

    # des：斜体 flavor 文本，整体灰色（无 italic 字体即普通字）
    if fork.des:
        cursor_y += FORK_DES_TOP_GAP - vw(8) if fork.buff_des else FORK_DES_TOP_GAP
        for line in wrap_text(
            draw, clean_rich_text(fork.des), fork_des_font, panel_w - FORK_INNER_PAD * 2, max_lines=2
        ):
            draw.text((body_x, cursor_y), line, font=fork_des_font, fill=COLOR_DES_TEXT, anchor="lt")
            cursor_y += int(fork_des_font.size) + FORK_LINE_GAP

    return head_h + SEC_BODY_GAP + panel_h


async def _draw_drive_card(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, item: CharacterSuitItem
) -> int:
    """H5：bg-#DCDCDC rounded， 顶部 icon+name+lev pill + 底部 #E9E9E9 panel(基础属性 + 附加属性)。"""
    x, y = xy
    pad_x = DRIVE_CARD_PAD_X
    pad_y = DRIVE_CARD_PAD_Y
    # 顶部 row
    top_inner_h = DRIVE_ICON_BG_W
    # 内嵌属性 panel
    main_props = item.main_properties
    add_props = item.properties
    main_h = (int(drive_title_font.size) + vw(1)) + max(1, len(main_props)) * DRIVE_PROP_ROW_H if main_props else 0
    add_h = (int(drive_title_font.size) + vw(2)) + max(1, len(add_props)) * DRIVE_PROP_ROW_H if add_props else 0
    inner_h = main_h + add_h + (vw(1) if main_h and add_h else 0)
    card_h = pad_y * 2 + top_inner_h + (vw(1) + inner_h if inner_h else 0)

    bg = Image.new("RGBA", (width, card_h), COLOR_INNER)
    canvas.paste(bg, (x, y), rounded_mask((width, card_h), DRIVE_CARD_RADIUS))

    # top row
    top_x = x + pad_x
    top_y = y + pad_y
    canvas.alpha_composite(DRIVE_CELL_BG_DRIVE, (top_x, top_y))
    drive_icon = _resize(await get_char_suit_drive_img(item.id), DRIVE_ICON_W) if item.id else None
    if drive_icon is not None:
        canvas.alpha_composite(
            drive_icon,
            (top_x + (DRIVE_ICON_BG_W - DRIVE_ICON_W) // 2, top_y + (DRIVE_ICON_BG_W - DRIVE_ICON_W) // 2),
        )
    name_x = top_x + DRIVE_ICON_BG_W + vw(3)
    draw.text((name_x, top_y + vw(2)), item.name, font=drive_name_font, fill=COLOR_BODY_TEXT, anchor="lt")
    pill_text = f"+{item.lev}"
    pill_w = round(draw.textlength(pill_text, font=drive_lev_font)) + DRIVE_LEV_PAD_X * 2
    pill_h = int(drive_lev_font.size) + DRIVE_LEV_PAD_Y * 2
    pill_y = top_y + int(drive_name_font.size) + vw(4)
    pill_bg = Image.new("RGBA", (pill_w, pill_h), COLOR_DRIVE_LEV_BG)
    canvas.paste(pill_bg, (name_x, pill_y), rounded_mask((pill_w, pill_h), vw(6)))
    draw.text(
        (name_x + pill_w // 2, pill_y + pill_h // 2),
        pill_text,
        font=drive_lev_font,
        fill=COLOR_DRIVE_LEV_TEXT,
        anchor="mm",
    )

    if not inner_h:
        return card_h

    # inner panel bg-#E9E9E9
    inner_x = x + vw(2)
    inner_y = top_y + top_inner_h + vw(1)
    inner_w_actual = width - vw(4)
    inner_bg = Image.new("RGBA", (inner_w_actual, inner_h), COLOR_INNER_LIGHT)
    canvas.paste(inner_bg, (inner_x, inner_y), rounded_mask((inner_w_actual, inner_h), vw(4)))

    cy = inner_y
    if main_props:
        draw.text((inner_x + vw(5), cy), "基础属性", font=drive_title_font, fill=COLOR_DRIVE_TITLE, anchor="lt")
        cy += int(drive_title_font.size) + vw(1)
        for prop in main_props:
            await _draw_drive_prop_row(canvas, draw, (inner_x, cy), inner_w_actual, prop, alt=False)
            cy += DRIVE_PROP_ROW_H
        if add_props:
            cy += vw(1)
    if add_props:
        draw.text((inner_x + vw(5), cy), "附加属性", font=drive_title_font, fill=COLOR_DRIVE_TITLE, anchor="lt")
        cy += int(drive_title_font.size) + vw(2)
        for idx, prop in enumerate(add_props):
            await _draw_drive_prop_row(canvas, draw, (inner_x, cy), inner_w_actual, prop, alt=(idx % 2 == 1))
            cy += DRIVE_PROP_ROW_H

    return card_h


async def _draw_drive_prop_row(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    prop: CharacterProperty,
    alt: bool,
) -> None:
    x, y = xy
    if alt:
        bg = Image.new("RGBA", (width, DRIVE_PROP_ROW_H), COLOR_DRIVE_PROP_BG_ALT)
        canvas.alpha_composite(bg, (x, y))
    else:
        bg = Image.new("RGBA", (width, DRIVE_PROP_ROW_H), (255, 255, 255, 255))
        canvas.alpha_composite(bg, (x, y))
    icon = _resize(await get_char_property_img(prop.id), DRIVE_PROP_ICON_W) if prop.id else None
    icon_x = x + vw(5)
    if icon is not None:
        canvas.alpha_composite(icon, (icon_x, y + (DRIVE_PROP_ROW_H - DRIVE_PROP_ICON_W) // 2))
    draw.text(
        (icon_x + DRIVE_PROP_ICON_W + vw(3), y + DRIVE_PROP_ROW_H // 2),
        _truncate(draw, prop.name, drive_prop_name_font, width - vw(80)),
        font=drive_prop_name_font,
        fill=COLOR_BODY_TEXT2,
        anchor="lm",
    )
    draw.text(
        (x + width - vw(8), y + DRIVE_PROP_ROW_H // 2),
        f"+{_format_value(prop.value)}",
        font=drive_prop_value_font,
        fill=COLOR_DRIVE_VALUE,
        anchor="rm",
    )


def _suit_section_h(suit: CharacterSuit, width: int) -> int:
    if not suit.id:
        return 0
    head_h = _section_header_h()
    suit_top_h = round(SUIT_TOP_BG.height * width / SUIT_TOP_BG.width)
    drives = [*suit.core, *suit.pie]
    drive_rows = (len(drives) + 1) // 2

    drives_h = 0
    for idx in range(drive_rows):
        row_max = 0
        for sub in drives[idx * 2 : idx * 2 + 2]:
            row_max = max(row_max, _drive_card_h(sub))
        drives_h += row_max
    drives_h += max(0, drive_rows - 1) * DRIVE_GRID_GAP_Y

    return head_h + SEC_BODY_GAP + suit_top_h + SUIT_TOP_BOTTOM_GAP + drives_h


def _drive_card_h(item: CharacterSuitItem) -> int:
    main_props = item.main_properties
    add_props = item.properties
    main_h = (int(drive_title_font.size) + vw(1)) + max(1, len(main_props)) * DRIVE_PROP_ROW_H if main_props else 0
    add_h = (int(drive_title_font.size) + vw(2)) + max(1, len(add_props)) * DRIVE_PROP_ROW_H if add_props else 0
    inner_h = main_h + add_h + (vw(1) if main_h and add_h else 0)
    return DRIVE_CARD_PAD_Y * 2 + DRIVE_ICON_BG_W + (vw(1) + inner_h if inner_h else 0)


async def _draw_suit(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], width: int, suit: CharacterSuit
) -> int:
    if not suit.id:
        return 0
    head_h = _draw_section_header(canvas, draw, xy, SECTION_ATTR_ICON, "空幕")
    cursor = xy[1] + head_h + SEC_BODY_GAP

    # suit_top_bg + 名字 + condition icons
    top_w = width
    top_h = round(SUIT_TOP_BG.height * top_w / SUIT_TOP_BG.width)
    top_bg = SUIT_TOP_BG.resize((top_w, top_h), Image.Resampling.LANCZOS)
    canvas.alpha_composite(top_bg, (xy[0], cursor))
    # 名字（白色，落在 suit_top_bg 顶部胶囊里）
    name_y = cursor + SUIT_NAME_TOP_GAP
    draw.text((xy[0] + top_w // 2, name_y), suit.name, font=suit_name_font, fill=COLOR_WHITE, anchor="mt")
    # condition icons row：官方 mt-vw-20，要落在 suit_top_bg 下半的浅灰区
    cond_y = name_y + int(suit_name_font.size) + SUIT_COND_TOP_GAP
    # condition list = [suit.id, "add", *suitCondition]
    items = [suit.id, "add", *suit.suit_condition] if suit.suit_condition else [suit.id]
    cond_total_w = 0
    cond_imgs: list[Image.Image | None] = []
    for it in items:
        if it == "add":
            cond_imgs.append(SUIT_COND_ADD)
            cond_total_w += SUIT_COND_ADD_W
        else:
            img = _resize(await get_char_suit_detail_img(it), SUIT_COND_ICON_W)
            cond_imgs.append(img)
            cond_total_w += SUIT_COND_ICON_W
    cond_total_w += max(0, len(items) - 1) * vw(4)
    cx = xy[0] + (top_w - cond_total_w) // 2
    for it, img in zip(items, cond_imgs):
        if img is None:
            cx += SUIT_COND_ICON_W + vw(4)
            continue
        if it == "add":
            canvas.alpha_composite(img, (cx, cond_y + (SUIT_COND_ICON_W - SUIT_COND_ADD_W) // 2))
            cx += SUIT_COND_ADD_W + vw(4)
        else:
            canvas.alpha_composite(img, (cx, cond_y))
            cx += SUIT_COND_ICON_W + vw(4)

    cursor += top_h + SUIT_TOP_BOTTOM_GAP

    # drives 2-col grid
    drives = [*suit.core, *suit.pie]
    card_w = (width - DRIVE_GRID_GAP_X) // 2
    for row_idx in range((len(drives) + 1) // 2):
        row_items = drives[row_idx * 2 : row_idx * 2 + 2]
        row_heights: list[int] = []
        for col_idx, item in enumerate(row_items):
            cx_card = xy[0] + col_idx * (card_w + DRIVE_GRID_GAP_X)
            h = await _draw_drive_card(canvas, draw, (cx_card, cursor), card_w, item)
            row_heights.append(h)
        cursor += max(row_heights) if row_heights else 0
        if row_idx < (len(drives) + 1) // 2 - 1:
            cursor += DRIVE_GRID_GAP_Y

    return cursor - xy[1]


def _measure(draw: ImageDraw.ImageDraw, character: CharacterDetail, inner_w: int) -> list[tuple[str, int]]:
    sections: list[tuple[str, int]] = [("portrait", PORTRAIT_IMG_H)]
    visible_props = _filter_props(character.properties)
    if visible_props:
        sections.append(("props", _section_header_h() + SEC_BODY_GAP + _props_panel_h(visible_props[:6])))

    skills = [s for s in character.skills if s.name]
    city = [s for s in character.city_skills if s.name]
    if skills or city:
        head_h = _section_header_h()
        h = head_h + SEC_BODY_GAP
        if skills:
            cell_h = _battle_skill_cell_h()
            # 估算 row 数
            used = SKILL_PANEL_PAD_X
            rows = 1
            for sk in skills:
                w = SKILL_CELL_SMALL_W if sk.type == "Passive" else SKILL_CELL_LARGE_W
                next_w = used + w + (SKILL_GAP_X if used > SKILL_PANEL_PAD_X else 0)
                if next_w > inner_w - SKILL_PANEL_PAD_X:
                    rows += 1
                    used = SKILL_PANEL_PAD_X + w
                else:
                    used = next_w
            grid_h = rows * cell_h + max(0, rows - 1) * SKILL_GAP_X
            h += SKILL_PANEL_PAD_Y * 2 + INNER_HEAD_ICON + INNER_HEAD_BOTTOM_GAP + grid_h + SEC_BODY_GAP
        if city:
            cell_h = _battle_skill_cell_h()
            h += SKILL_PANEL_PAD_Y * 2 + INNER_HEAD_ICON + CITY_HEAD_BOTTOM_GAP + cell_h
        sections.append(("skills", h))

    if character.fork.id:
        sections.append(("fork", _section_header_h() + SEC_BODY_GAP + _fork_panel_h(draw, character.fork, inner_w)))

    if character.suit.id:
        sections.append(("suit", _suit_section_h(character.suit, inner_w)))

    return sections


async def draw_character_card_img(ev: Event, character: CharacterDetail, role_name: str, uid: str):
    user_avatar = await get_event_avatar(ev)

    inner_w = WIDTH - PADDING * 2 - OUTER_PAD_X * 2
    measure_canvas = Image.new("RGBA", (1, 1))
    measure_draw = ImageDraw.Draw(measure_canvas)
    sections = _measure(measure_draw, character, inner_w)
    body_h = sum(h for _, h in sections) + max(0, len(sections) - 1) * SECTION_GAP
    outer_h = body_h + OUTER_PAD_Y * 2

    body_top = 258
    total_h = body_top + outer_h + FOOTER_RESERVE

    canvas = get_nte_bg(WIDTH, total_h).convert("RGBA")
    title = make_nte_role_title(user_avatar, role_name, uid).resize((1024, 201), Image.Resampling.LANCZOS)
    canvas.alpha_composite(title, (PADDING, 30))
    draw = ImageDraw.Draw(canvas)

    outer_x = PADDING
    outer_w = WIDTH - PADDING * 2
    outer_panel = Image.new("RGBA", (outer_w, outer_h), COLOR_OUTER)
    canvas.paste(outer_panel, (outer_x, body_top), rounded_mask((outer_w, outer_h), OUTER_RADIUS))

    inner_x = outer_x + OUTER_PAD_X
    cursor = body_top + OUTER_PAD_Y
    section_map = dict(sections)
    for kind, _ in sections:
        if kind == "portrait":
            await _draw_portrait(canvas, draw, (inner_x, cursor), inner_w, character)
        elif kind == "props":
            await _draw_props(canvas, draw, (inner_x, cursor), inner_w, character.properties)
        elif kind == "skills":
            await _draw_skills(canvas, draw, (inner_x, cursor), inner_w, character)
        elif kind == "fork":
            await _draw_fork(canvas, draw, (inner_x, cursor), inner_w, character.fork)
        elif kind == "suit":
            await _draw_suit(canvas, draw, (inner_x, cursor), inner_w, character.suit)
        cursor += section_map[kind] + SECTION_GAP

    add_footer(canvas)
    return await convert_img(canvas)
