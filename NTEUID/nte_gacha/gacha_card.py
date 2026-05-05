from __future__ import annotations

from pathlib import Path
from datetime import datetime

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from .gacha_model import NTEGachaItem, NTEGachaSection, NTEGachaSummary
from ..utils.image import (
    add_footer,
    get_nte_bg,
    open_texture,
    rounded_mask,
    char_img_ring,
    make_nte_role_title,
)
from ..utils.resource.cdn import get_avatar_img, get_weapon_img
from ..utils.fonts.nte_fonts import nte_font_bold, nte_font_origin

_TEX = Path(__file__).parent / "texture2d"
_MOOD_TEX = _TEX / "mood"
_WHITE = (255, 255, 255)
_SUB = (210, 215, 230)

_SSR_RATING_TABLE = (
    (15, "欧气附体天选人"),
    (40, "协议签订幸运儿"),
    (60, "普普通通路人王"),
    (75, "伊波恩打工仔"),
    (10**9, "异象重点关照对象"),
)
_NO_SSR_RATING_TABLE = ((50, "囤囤鼠"), (10**9, "薛定谔的抽卡人"))
_BANNER_RANK = {"限定卡池": 0, "弧盘池": 1, "常驻卡池": 2}
_PAGE_W = 1100
_ITEM_GRID_X = 65
_ITEM_W = 150
_ITEM_H = _ITEM_W * 340 // 240
_ITEM_GAP = 14
_ITEM_STRIDE = 225
_ITEMS_PER_ROW = 6
_MAX_ITEMS_PER_SECTION = 12
_BANNER_H = 192
_BANNER_ITEMS_OFFSET = 147
_SECTION_GAP = 12
_TITLE_Y = 12
_TITLE_H = 216
_TITLE_SECTION_GAP = 9
_BOTTOM_PAD = 24
_FOOTER_RESERVE = 60


def _item_rows(item_count: int) -> int:
    return (min(item_count, _MAX_ITEMS_PER_SECTION) + _ITEMS_PER_ROW - 1) // _ITEMS_PER_ROW


def _section_h(item_count: int) -> int:
    if item_count <= 0:
        return _BANNER_H
    return _BANNER_ITEMS_OFFSET + (_item_rows(item_count) - 1) * _ITEM_STRIDE + _ITEM_H


def _rating(total: int, ssr: int) -> str:
    # i_api23try.gacha_basic.constant 内嵌：SSR 走 总抽/总S，无 SSR 走 总抽数
    if ssr > 0:
        return _SSR_RATING_TABLE[_rating_index(total, ssr)][1]
    return next(label for threshold, label in _NO_SSR_RATING_TABLE if total <= threshold)


def _rating_index(total: int, ssr: int) -> int:
    if ssr <= 0:
        return -1
    avg = total / ssr
    return next(index for index, (threshold, _) in enumerate(_SSR_RATING_TABLE) if avg <= threshold)


def _rating_mood_path(total: int, ssr: int) -> Path:
    index = _rating_index(total, ssr)
    path = _MOOD_TEX / f"{index:02d}.png"
    return path if index >= 0 and path.exists() else _MOOD_TEX / "default.png"


def _draw_title_stats(canvas: Image.Image, title_y: int, total: int, ssr: int) -> None:
    right = _PAGE_W - 21 - 75
    mid = title_y + 108 + 30
    draw = ImageDraw.Draw(canvas)
    f_num, f_unit, f_tier = nte_font_bold(48), nte_font_origin(24), nte_font_bold(30)
    sk = (0, 0, 0, 230)
    unit_w = draw.textlength("抽", font=f_unit)
    row1_b = mid - 6
    draw.text((right, row1_b), "抽", font=f_unit, fill=_SUB, anchor="rb", stroke_width=2, stroke_fill=sk)
    draw.text(
        (right - unit_w - 6, row1_b), str(total), font=f_num, fill=_WHITE, anchor="rb", stroke_width=2, stroke_fill=sk
    )
    draw.text(
        (right, mid + 12), _rating(total, ssr), font=f_tier, fill=_WHITE, anchor="rt", stroke_width=2, stroke_fill=sk
    )


def _banner_texture(section: NTEGachaSection) -> Path:
    name = section.banner_type or section.banner_name
    if "弧盘" in name:
        return _TEX / "purple.png"
    if "限定" in name:
        return _TEX / "pink.png"
    return _TEX / "blue.png"


def _format_date(ts: int) -> str:
    return datetime.fromtimestamp(ts).strftime("%Y.%m.%d")


def _section_subtitle(section: NTEGachaSection) -> str:
    if section.begin_time_ts and section.end_time_ts:
        return f"{_format_date(section.begin_time_ts)} ~ {_format_date(section.end_time_ts)}"
    if section.begin_time_ts:
        return f"开始 {_format_date(section.begin_time_ts)}"
    if section.end_time_ts:
        return f"截至 {_format_date(section.end_time_ts)}"
    pull_times = [item.pull_time_ts for item in section.items if item.pull_time_ts > 0]
    if pull_times:
        return f"{_format_date(min(pull_times))} ~ {_format_date(max(pull_times))}"
    return ""


def _truncate(draw: ImageDraw.ImageDraw, text: str, font, max_w: int, suffix: str = "...") -> str:
    if draw.textlength(text, font=font) <= max_w:
        return text
    while text and draw.textlength(text + suffix, font=font) > max_w:
        text = text[:-1]
    return text + suffix if text else suffix


async def _load_gacha_icon(item_id: str) -> Image.Image | None:
    if item_id.startswith("fork_"):
        return await get_weapon_img(item_id)
    if item_id.isdigit():
        return await get_avatar_img(item_id)
    return None


def _draw_banner_stats(draw: ImageDraw.ImageDraw, cy: int, section: NTEGachaSection) -> None:
    f_num = nte_font_bold(36)
    f_label = nte_font_bold(18)
    values = [
        str(section.total_pull_count),
        str(section.ssr_count),
        str(section.avg_pity) if section.ssr_count > 0 else "—",
    ]
    labels = ["总抽数", "S数", "平均抽数"]

    for x, value, label in zip((700, 823, 938), values, labels, strict=True):
        draw.text((x, cy + 77), value, font=f_num, fill=_WHITE, anchor="mm", stroke_width=2, stroke_fill=(0, 0, 0, 110))
        draw.text(
            (x, cy + 113),
            label,
            font=f_label,
            fill=_WHITE,
            anchor="mm",
            stroke_width=2,
            stroke_fill=(0, 0, 0, 110),
        )


def _draw_banner(canvas: Image.Image, xy: tuple[int, int], section: NTEGachaSection) -> None:
    bg = open_texture(_banner_texture(section)).convert("RGBA")
    canvas.alpha_composite(bg, xy)

    cx, cy = xy
    draw = ImageDraw.Draw(canvas)
    icon = open_texture(_rating_mood_path(section.total_pull_count, section.ssr_count), size=(132, 132))
    canvas.alpha_composite(icon, (cx + 95, cy + 30))

    title_font = nte_font_bold(40)
    title_x = cx + 228
    title = _truncate(draw, section.banner_name, title_font, 315)
    draw.text(
        (title_x, cy + 78),
        title,
        font=title_font,
        fill=_WHITE,
        anchor="lm",
        stroke_width=2,
        stroke_fill=(0, 0, 0, 120),
    )

    subtitle = _section_subtitle(section)
    if subtitle:
        draw.text((title_x, cy + 123), subtitle, font=nte_font_bold(26), fill=_SUB, anchor="lm")

    _draw_banner_stats(draw, cy, section)


async def _draw_item(canvas: Image.Image, xy: tuple[int, int], item: NTEGachaItem, cell_bg: Image.Image) -> None:
    w, h = _ITEM_W, _ITEM_H
    cell = cell_bg.copy()
    avatar = await _load_gacha_icon(item.item_id)
    if avatar is not None:
        rs = w * 230 // 240
        cell.alpha_composite(char_img_ring(avatar.convert("RGBA"), rs), ((w - rs) // 2, h * 48 // 340))

    draw = ImageDraw.Draw(cell)
    f_name = nte_font_origin(16)
    name = _truncate(draw, item.item_name.removesuffix("角色卡"), f_name, w - 30, "…")
    draw.text((w // 2, h * 292 // 340), name, font=f_name, fill=_WHITE, anchor="mm")

    f_pull = nte_font_bold(16)
    pull_text = f"{item.pity}抽"
    pw = int(draw.textlength(pull_text, font=f_pull)) + 21
    ph = 28
    px, py = w - pw - 15, h * 200 // 340
    # ≤30 欧 / ≤80 平稳 / 其余 非
    color = (26, 191, 76) if item.pity <= 30 else (234, 129, 59) if item.pity <= 80 else (250, 58, 61)
    cell.paste(Image.new("RGBA", (pw, ph), (*color, 235)), (px, py), rounded_mask((pw, ph), ph // 2))
    draw.text((px + pw // 2, py + ph // 2), pull_text, font=f_pull, fill=_WHITE, anchor="mm")
    canvas.alpha_composite(cell, xy)


async def _draw_section(canvas: Image.Image, top_y: int, section: NTEGachaSection) -> int:
    _draw_banner(canvas, (0, top_y), section)
    items_top = top_y + _BANNER_ITEMS_OFFSET
    items = sorted(section.items, key=lambda i: i.pull_time_ts, reverse=True)[:_MAX_ITEMS_PER_SECTION]
    if not items:
        return top_y + _BANNER_H

    cell_bg = open_texture(_TEX / "char_bg.png", size=(_ITEM_W, _ITEM_H))
    for idx, item in enumerate(items):
        row, col = divmod(idx, _ITEMS_PER_ROW)
        await _draw_item(
            canvas,
            (_ITEM_GRID_X + col * (_ITEM_W + _ITEM_GAP), items_top + row * _ITEM_STRIDE),
            item,
            cell_bg,
        )
    return items_top + (_item_rows(len(items)) - 1) * _ITEM_STRIDE + _ITEM_H


async def draw_gacha_summary_img(
    ev: Event,
    summary: NTEGachaSummary,
    *,
    role_name: str,
    role_id: str,
) -> bytes:
    sections = sorted(
        (s for s in summary.sections if s.total_pull_count > 0),
        key=lambda s: _BANNER_RANK.get(s.banner_name, _BANNER_RANK.get(s.banner_type, 99)),
    )

    total_h = (
        _TITLE_Y
        + _TITLE_H
        + _TITLE_SECTION_GAP
        + sum(_section_h(len(s.items)) for s in sections)
        + max(0, len(sections) - 1) * _SECTION_GAP
        + _BOTTOM_PAD
        + _FOOTER_RESERVE
    )

    canvas = get_nte_bg(_PAGE_W, total_h, "bg2")
    canvas.alpha_composite(
        make_nte_role_title(await get_event_avatar(ev), role_name, role_id),
        (0, _TITLE_Y),
    )

    o = summary.overview
    assert o is not None  # 调用方已用 summary.is_empty 过滤
    _draw_title_stats(canvas, _TITLE_Y, o.total_pull_count, o.total_ssr_count)

    cursor = _TITLE_Y + _TITLE_H + _TITLE_SECTION_GAP
    for idx, section in enumerate(sections):
        cursor = await _draw_section(canvas, cursor, section)
        if idx < len(sections) - 1:
            cursor += _SECTION_GAP

    return await convert_img(add_footer(canvas))
