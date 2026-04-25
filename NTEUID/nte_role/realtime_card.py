from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    COLOR_OVERLAY,
    COLOR_SUBTEXT,
    add_footer,
    get_nte_bg,
    get_nte_title_bg,
    make_head_avatar,
)
from ..utils.fonts.nte_fonts import (
    nte_font_30,
    nte_font_42,
    nte_font_origin,
)
from ..utils.sdk.tajiduo_model import RoleHome

WIDTH = 1080
PADDING = 36
HEADER_HEIGHT = 152
FOOTER_RESERVE = 80
AVATAR_SIZE = 200
AVATAR_INNER = 160
AVATAR_OVERSHOOT_BELOW = 67
AVATAR_X = PADDING
AVATAR_Y = HEADER_HEIGHT - (AVATAR_SIZE - AVATAR_OVERSHOOT_BELOW)
BODY_TOP_GAP = 32

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "realtime"

SCALE = 1080 / 390
PAGE_PAD_X = round(15 * SCALE)
CONTENT_WIDTH = WIDTH - PAGE_PAD_X * 2

SEC_ICON_SIZE = round(18 * SCALE)
SEC_TITLE_FONT_SIZE = round(18 * SCALE)
SEC_SUB_FONT_SIZE = max(10, round(4 * SCALE))
SEC_TITLE_GAP = round(2 * SCALE)
SEC_BLOCK_HEIGHT_GAP = round(15 * SCALE)

STAT_ICON_SIZE = round(44 * SCALE)
STAT_NUM_FONT = round(13 * SCALE)
STAT_NAME_FONT = round(10 * SCALE)
STAT_INNER_GAP = round(2 * SCALE)
TOP_ROW_OVERLAY_Y = round(29 * SCALE)
ROW_GAP = round(33 * SCALE)
SIDE_INSET = round(16 * SCALE)
BAR_LABEL_FONT = round(13 * SCALE)
BAR_VALUE_FONT = round(17 * SCALE)
BAR_GAP = round(5 * SCALE)
SEPARATOR_HEIGHT = round(14 * SCALE)

COLOR_SECTION_TITLE = (240, 240, 245)
COLOR_SUBTITLE_GRAY = (177, 177, 177)
COLOR_STAT_NUM = (65, 65, 65)
COLOR_STAT_NAME = (122, 122, 122)
COLOR_BAR_LABEL = COLOR_WHITE
COLOR_BAR_VALUE = COLOR_WHITE
COLOR_DAY_VALUE = (235, 104, 119)
COLOR_SEPARATOR = (239, 239, 239)

SUBTITLE_TEXT = "REAL - TIME INFOMATION"

sec_title_font = nte_font_origin(SEC_TITLE_FONT_SIZE)
sec_sub_font = nte_font_origin(SEC_SUB_FONT_SIZE)
stat_num_font = nte_font_origin(STAT_NUM_FONT)
stat_name_font = nte_font_origin(STAT_NAME_FONT)
bar_label_font = nte_font_origin(BAR_LABEL_FONT)
bar_value_font = nte_font_origin(BAR_VALUE_FONT)


def _load_icon(name: str, size: int) -> Image.Image:
    return Image.open(TEXTURE_PATH / name).convert("RGBA").resize((size, size), Image.Resampling.LANCZOS)


SEC_ICON = _load_icon("sec_icon.png", SEC_ICON_SIZE)
STAMINA_ICON = _load_icon("stamina.png", STAT_ICON_SIZE)
CITYSTAMINA_ICON = _load_icon("citystamina.png", STAT_ICON_SIZE)

_BG_RAW = Image.open(TEXTURE_PATH / "bg.png").convert("RGBA")
BG_IMG_W = CONTENT_WIDTH
BG_IMG_H = round(BG_IMG_W * _BG_RAW.height / _BG_RAW.width)
BG_IMG = _BG_RAW.resize((BG_IMG_W, BG_IMG_H), Image.Resampling.LANCZOS)

SECTION_HEADER_HEIGHT = max(
    SEC_ICON_SIZE,
    int(sec_title_font.size) + SEC_TITLE_GAP + int(sec_sub_font.size),
)


def _city_stamina_max(tycoon_level: int) -> int:
    """官方根据大亨等级推都市活力上限：>=23→700, >=16→500, >=10→350, >=5→200, 否则 100。"""
    for threshold, limit in ((23, 700), (16, 500), (10, 350), (5, 200)):
        if tycoon_level >= threshold:
            return limit
    return 100


def _draw_section_header(canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int]) -> None:
    x, y = xy
    canvas.alpha_composite(SEC_ICON, (x, y))
    text_x = x + SEC_ICON_SIZE + round(2 * SCALE)
    draw.text((text_x, y), "实时信息", font=sec_title_font, fill=COLOR_SECTION_TITLE, anchor="lt")
    title_bottom = draw.textbbox((text_x, y), "实时信息", font=sec_title_font, anchor="lt")[3]
    draw.text(
        (text_x, title_bottom + SEC_TITLE_GAP),
        SUBTITLE_TEXT,
        font=sec_sub_font,
        fill=COLOR_SUBTITLE_GRAY,
        anchor="lt",
    )


def _draw_stat_block(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    icon: Image.Image,
    name: str,
    num: str,
    xy: tuple[int, int],
) -> None:
    """[icon] [num/name] 横向块，按官方 Fp 组件对齐：icon 左、文本右。"""
    x, y = xy
    icon_y = y
    canvas.alpha_composite(icon, (x, icon_y))
    text_x = x + STAT_ICON_SIZE + STAT_INNER_GAP
    cy = icon_y + STAT_ICON_SIZE // 2
    draw.text((text_x, cy - round(2 * SCALE)), num, font=stat_num_font, fill=COLOR_STAT_NUM, anchor="lb")
    draw.text((text_x, cy + round(2 * SCALE)), name, font=stat_name_font, fill=COLOR_STAT_NAME, anchor="lt")


def _draw_bottom_cell(
    draw: ImageDraw.ImageDraw,
    label: str,
    value: str,
    cx: int,
    cy: int,
    *,
    value_color: tuple[int, int, int] = COLOR_BAR_VALUE,
    after_value: str = "",
) -> None:
    """`label: value` 横向，cx 为该单元水平中心。"""
    label_w = draw.textlength(label, font=bar_label_font)
    value_w = draw.textlength(value, font=bar_value_font)
    after_w = draw.textlength(after_value, font=bar_value_font) if after_value else 0
    gap = BAR_GAP
    total = label_w + gap + value_w + after_w
    start_x = cx - total // 2
    draw.text((start_x, cy), label, font=bar_label_font, fill=COLOR_BAR_LABEL, anchor="lm")
    val_x = start_x + label_w + gap
    draw.text((val_x, cy), value, font=bar_value_font, fill=value_color, anchor="lm")
    if after_value:
        draw.text((val_x + value_w, cy), after_value, font=bar_value_font, fill=COLOR_BAR_VALUE, anchor="lm")


async def draw_realtime_img(ev: Event, home: RoleHome, role_name: str):
    user_avatar = await get_event_avatar(ev)
    avatar_block = make_head_avatar(user_avatar, size=AVATAR_SIZE, avatar_size=AVATAR_INNER)

    body_top = AVATAR_Y + AVATAR_SIZE + BODY_TOP_GAP
    card_h = SECTION_HEADER_HEIGHT + SEC_BLOCK_HEIGHT_GAP + BG_IMG_H
    total_height = body_top + card_h + FOOTER_RESERVE

    canvas = get_nte_bg(WIDTH, total_height).convert("RGBA")
    canvas.paste(get_nte_title_bg(WIDTH, HEADER_HEIGHT), (0, 0))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEADER_HEIGHT), COLOR_OVERLAY), (0, 0))

    draw = ImageDraw.Draw(canvas)
    title_right = WIDTH - PADDING
    draw.text((title_right, 34), "异环·实时信息", font=nte_font_42, fill=COLOR_WHITE, anchor="ra")
    draw.text((title_right, 96), role_name, font=nte_font_30, fill=COLOR_SUBTEXT, anchor="ra")
    canvas.alpha_composite(avatar_block, (AVATAR_X, AVATAR_Y))

    _draw_section_header(canvas, draw, (PAGE_PAD_X, body_top))

    bg_y = body_top + SECTION_HEADER_HEIGHT + SEC_BLOCK_HEIGHT_GAP
    canvas.alpha_composite(BG_IMG, (PAGE_PAD_X, bg_y))

    # 上半行：本性像素 + 都市活力（白底区）
    stamina_max = home.stamina_max_value or 240
    citystamina_max = home.city_stamina_max_value or _city_stamina_max(home.tycoon_level)
    overlay_top_y = bg_y + TOP_ROW_OVERLAY_Y
    inner_left = PAGE_PAD_X + SIDE_INSET
    inner_right = PAGE_PAD_X + BG_IMG_W - SIDE_INSET
    inner_w = inner_right - inner_left
    half_w = inner_w // 2

    _draw_stat_block(
        canvas,
        draw,
        STAMINA_ICON,
        "本性像素",
        f"{home.stamina_value}/{stamina_max}",
        (inner_left + (half_w - STAT_ICON_SIZE - round(80 * SCALE) // 2) // 2, overlay_top_y),
    )
    _draw_stat_block(
        canvas,
        draw,
        CITYSTAMINA_ICON,
        "都市活力",
        f"{home.city_stamina_value}/{citystamina_max}",
        (inner_left + half_w + (half_w - STAT_ICON_SIZE - round(80 * SCALE) // 2) // 2, overlay_top_y),
    )

    # 下半行：活跃度 + | + 周本次数（深底区）
    bottom_band_y = bg_y + BG_IMG_H - round(46 * SCALE)
    third = inner_w // 3
    cy = bottom_band_y + round(20 * SCALE)
    sep_x = inner_left + inner_w // 2
    draw.line(
        [(sep_x, cy - SEPARATOR_HEIGHT // 2), (sep_x, cy + SEPARATOR_HEIGHT // 2)],
        fill=COLOR_SEPARATOR,
        width=2,
    )
    _draw_bottom_cell(
        draw,
        "活跃度:",
        str(home.day_value),
        inner_left + third // 2 + round(40 * SCALE),
        cy,
        value_color=COLOR_DAY_VALUE,
        after_value="/100",
    )
    _draw_bottom_cell(
        draw,
        "周本次数:",
        f"{home.week_copies_remain_cnt}/3",
        inner_left + inner_w - third // 2 - round(40 * SCALE),
        cy,
    )

    add_footer(canvas)
    return await convert_img(canvas)
