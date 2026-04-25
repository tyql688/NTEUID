from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageFont

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    COLOR_OVERLAY,
    COLOR_SUBTEXT,
    add_footer,
    get_nte_bg,
    rounded_mask,
    get_nte_title_bg,
    make_head_avatar,
)
from ..utils.resource.cdn import get_area_type_img, get_area_wide_img
from ..utils.fonts.nte_fonts import (
    nte_font_30,
    nte_font_42,
    nte_font_origin,
)
from ..utils.sdk.tajiduo_model import AreaProgress, AreaDetailItem

WIDTH = 1080
PADDING = 36
HEADER_HEIGHT = 152
FOOTER_RESERVE = 80
AVATAR_SIZE = 200
AVATAR_INNER = 160
AVATAR_OVERSHOOT_BELOW = 67  # 头像 2/3 在 title 内、1/3 探入 body
AVATAR_X = PADDING
AVATAR_Y = HEADER_HEIGHT - (AVATAR_SIZE - AVATAR_OVERSHOOT_BELOW)
BODY_TOP_GAP = 32

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "explore"

# vw 系数：官方 design-width=390，渲染宽 1080
SCALE = 1080 / 390
PAGE_PAD_X = round(15 * SCALE)
CARD_PAD = round(5 * SCALE)
CARD_GAP = round(15 * SCALE)
CARD_RADIUS = round(12 * SCALE)
CARD_BOTTOM_PAD = round(17 * SCALE)
BANNER_OFFSET_TOP = round(97 * SCALE)
BANNER_INFO_BIAS = round(5 * SCALE)  # 信息行垂直中心相对 city_bottom 几何中心的下移量
PIN_SIZE = round(16 * SCALE)
BOOK_SIZE = round(16 * SCALE)
NAME_GAP = round(5 * SCALE)
NAME_FONT_SIZE = round(15 * SCALE)
PROGRESS_BAR_HEIGHT = round(10 * SCALE)
BIG_NUM_FONT_SIZE = round(24 * SCALE)
BIG_LABEL_FONT_SIZE = round(11 * SCALE)
BIG_NUM_BLOCK_W = round(45 * SCALE)
BIG_NUM_BLOCK_MARGIN = round(15 * SCALE)
INFO_BLOCK_LEFT_MARGIN = round(15 * SCALE)
SUB_TITLE_FONT = round(13 * SCALE)
SUB_TITLE_GAP = round(2 * SCALE)
SUB_HEADER_TOP = round(5 * SCALE)
SUB_GRID_TOP = round(5 * SCALE)
SUB_ROW_GAP = round(5 * SCALE)
SUB_CELL_W = round(110 * SCALE)
SUB_CELL_H = round(35 * SCALE)
SUB_TYPE_ICON = round(35 * SCALE)
SUB_NAME_FONT = round(10 * SCALE)
SUB_VALUE_FONT = round(10 * SCALE)
SUB_RIGHT_PAD = round(8 * SCALE)
CONTENT_WIDTH = WIDTH - PAGE_PAD_X * 2
CARD_INNER_W = CONTENT_WIDTH - CARD_PAD * 2

COLOR_CARD_BG = (255, 255, 255, 255)
COLOR_CARD_BORDER = (229, 229, 229, 255)
COLOR_NAME_PINK = (255, 89, 149)
COLOR_BIG_NUM = (216, 216, 216)
COLOR_BIG_LABEL = (149, 149, 149)
COLOR_SUB_TITLE = (83, 83, 83)
COLOR_SUB_NAME = (56, 56, 56)
COLOR_SUB_FOUND_LABEL = (125, 125, 125)
COLOR_SUB_VALUE = (196, 89, 81)
COLOR_PROGRESS_BG = (0, 0, 0)
COLOR_PROGRESS_FILL = (124, 236, 252)

name_font = nte_font_origin(NAME_FONT_SIZE)
big_num_font = nte_font_origin(BIG_NUM_FONT_SIZE)
big_label_font = nte_font_origin(BIG_LABEL_FONT_SIZE)
sub_title_font = nte_font_origin(SUB_TITLE_FONT)
sub_name_font = nte_font_origin(SUB_NAME_FONT)
sub_value_font = nte_font_origin(SUB_VALUE_FONT)


def _load_pin() -> Image.Image:
    return Image.open(TEXTURE_PATH / "pin.png").convert("RGBA").resize((PIN_SIZE, PIN_SIZE), Image.Resampling.LANCZOS)


def _load_book() -> Image.Image:
    return (
        Image.open(TEXTURE_PATH / "book.png").convert("RGBA").resize((BOOK_SIZE, BOOK_SIZE), Image.Resampling.LANCZOS)
    )


def _load_city_bottom() -> tuple[Image.Image, int]:
    raw = Image.open(TEXTURE_PATH / "city_bottom.png").convert("RGBA")
    h = round(CARD_INNER_W * raw.height / raw.width)
    return raw.resize((CARD_INNER_W, h), Image.Resampling.LANCZOS), h


def _load_sub_bg() -> Image.Image:
    return (
        Image.open(TEXTURE_PATH / "location_bg.png")
        .convert("RGBA")
        .resize((SUB_CELL_W, SUB_CELL_H), Image.Resampling.LANCZOS)
    )


PIN_ICON = _load_pin()
BOOK_ICON = _load_book()
CITY_BOTTOM, CITY_BOTTOM_H = _load_city_bottom()
SUB_CELL_BG = _load_sub_bg()

GRID_W = CARD_INNER_W - CARD_PAD * 2
GRID_COL_GAP = max(0, (GRID_W - SUB_CELL_W * 3) // 2)
SUB_TITLE_BLOCK_H = max(BOOK_SIZE, int(sub_title_font.size))


@dataclass(slots=True)
class PreparedArea:
    area: AreaProgress
    banner: Image.Image
    rows: list[tuple[AreaDetailItem, Image.Image | None]]
    banner_h: int


def _truncate(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.FreeTypeFont, max_width: int) -> str:
    """超宽就尾部截断加 `...`，对应官方 `line-clamp-1` 等价行为。"""
    if draw.textlength(text, font=font) <= max_width:
        return text
    suffix = "..."
    truncated = text
    while truncated and draw.textlength(truncated + suffix, font=font) > max_width:
        truncated = truncated[:-1]
    return truncated + suffix


async def _load_area_banner(area_id: str, target_w: int) -> Image.Image:
    """area/wide 走 `w-full` 自适应：按目标宽度等比缩放。下载失败回退灰底，避免连累整张图渲染。"""
    try:
        image = await get_area_wide_img(area_id)
    except OSError:
        return Image.new("RGBA", (target_w, round(target_w * 248 / 684)), (180, 180, 180, 255))
    image = image.convert("RGBA")
    new_h = round(image.height * target_w / image.width)
    return image.resize((target_w, new_h), Image.Resampling.LANCZOS)


async def _load_sub_icon(type_id: str) -> Image.Image | None:
    """子项类型图标下载失败返回 None，由调用方跳过。"""
    try:
        image = await get_area_type_img(type_id)
    except OSError:
        return None
    return image.convert("RGBA").resize((SUB_TYPE_ICON, SUB_TYPE_ICON), Image.Resampling.LANCZOS)


def _draw_progress_bar(canvas: Image.Image, xy: tuple[int, int], w: int, ratio: float) -> None:
    x, y = xy
    bg = Image.new("RGBA", (w, PROGRESS_BAR_HEIGHT), COLOR_PROGRESS_BG)
    canvas.paste(bg, (x, y), rounded_mask((w, PROGRESS_BAR_HEIGHT), PROGRESS_BAR_HEIGHT // 2))
    fill_w = max(0, min(w, round(w * min(ratio, 1.0))))
    if fill_w > 0:
        fill = Image.new("RGBA", (fill_w, PROGRESS_BAR_HEIGHT), COLOR_PROGRESS_FILL)
        canvas.paste(fill, (x, y), rounded_mask((fill_w, PROGRESS_BAR_HEIGHT), PROGRESS_BAR_HEIGHT // 2))


def _draw_sub_cell(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    sub: AreaDetailItem,
    icon: Image.Image | None,
    xy: tuple[int, int],
) -> None:
    x, y = xy
    canvas.alpha_composite(SUB_CELL_BG, (x, y))
    cy = y + SUB_CELL_H // 2
    icon_x = x + round(1 * SCALE)
    if icon is not None:
        canvas.alpha_composite(icon, (icon_x, cy - SUB_TYPE_ICON // 2))
    text_x = icon_x + SUB_TYPE_ICON + round(2 * SCALE)
    text_max_w = SUB_CELL_W - (text_x - x) - SUB_RIGHT_PAD
    name_y = cy - round(8 * SCALE)
    draw.text(
        (text_x, name_y),
        _truncate(draw, sub.name, sub_name_font, text_max_w),
        font=sub_name_font,
        fill=COLOR_SUB_NAME,
        anchor="lm",
    )
    found_y = cy + round(8 * SCALE)
    progress = sub.progress or 0
    label_w = draw.textlength("已发现:", font=sub_name_font)
    draw.text((text_x, found_y), "已发现:", font=sub_name_font, fill=COLOR_SUB_FOUND_LABEL, anchor="lm")
    draw.text(
        (text_x + label_w + round(2 * SCALE), found_y),
        f"{progress}/{sub.total}",
        font=sub_value_font,
        fill=COLOR_SUB_VALUE,
        anchor="lm",
    )


def _card_height(detail_count: int, banner_h: int) -> int:
    rows = (detail_count + 2) // 3
    sub_section_h = (
        SUB_HEADER_TOP + SUB_TITLE_BLOCK_H + SUB_GRID_TOP + rows * SUB_CELL_H + max(0, rows - 1) * SUB_ROW_GAP
    )
    return banner_h + sub_section_h + CARD_BOTTOM_PAD + CARD_PAD * 2


def _banner_total_height(area_image_h: int) -> int:
    """官方两层叠放：layer-0 area 图 + layer-1（mt-vw-97）= city_bottom 装饰条。
    总高 = max(area 图实际高, mt-97 + city_bottom 高)。"""
    return max(area_image_h, BANNER_OFFSET_TOP + CITY_BOTTOM_H)


def _draw_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    item: PreparedArea,
    y: int,
) -> int:
    """单张区域卡：白底圆角 + banner + 信息行 + 子项 grid。返回卡片底 y。"""
    card_x = PAGE_PAD_X
    card_h = _card_height(len(item.rows), item.banner_h)
    bg_layer = Image.new("RGBA", (CONTENT_WIDTH, card_h), COLOR_CARD_BG)
    canvas.paste(bg_layer, (card_x, y), rounded_mask((CONTENT_WIDTH, card_h), CARD_RADIUS))
    border = Image.new("RGBA", (CONTENT_WIDTH, card_h), (0, 0, 0, 0))
    ImageDraw.Draw(border).rounded_rectangle(
        (0, 0, CONTENT_WIDTH - 1, card_h - 1), radius=CARD_RADIUS, outline=COLOR_CARD_BORDER, width=1
    )
    canvas.alpha_composite(border, (card_x, y))

    inner_x = card_x + CARD_PAD
    inner_y = y + CARD_PAD
    banner_w = CARD_INNER_W
    canvas.paste(
        item.banner,
        (inner_x, inner_y),
        rounded_mask((banner_w, item.banner.height), CARD_RADIUS),
    )
    city_bottom_y = inner_y + BANNER_OFFSET_TOP
    canvas.alpha_composite(CITY_BOTTOM, (inner_x, city_bottom_y))

    band_center_y = city_bottom_y + CITY_BOTTOM_H // 2 + BANNER_INFO_BIAS

    # 右块（大数字 + 探索值 标签）
    right_block_x = inner_x + banner_w - BIG_NUM_BLOCK_MARGIN - BIG_NUM_BLOCK_W
    right_block_cx = right_block_x + BIG_NUM_BLOCK_W // 2
    num_h = sum(big_num_font.getmetrics())
    label_h = sum(big_label_font.getmetrics())
    right_top_y = band_center_y - (num_h + round(2 * SCALE) + label_h) // 2
    draw.text(
        (right_block_cx, right_top_y),
        str(item.area.progress),
        font=big_num_font,
        fill=COLOR_BIG_NUM,
        anchor="mt",
    )
    draw.text(
        (right_block_cx, right_top_y + num_h + round(2 * SCALE)),
        "探索值",
        font=big_label_font,
        fill=COLOR_BIG_LABEL,
        anchor="mt",
    )

    # 左块（pin + 区域名 + 进度条）
    left_x = inner_x + INFO_BLOCK_LEFT_MARGIN
    left_w = right_block_x - left_x - round(8 * SCALE)
    name_h = max(PIN_SIZE, sum(name_font.getmetrics()))
    left_top_y = band_center_y - (name_h + round(3 * SCALE) + PROGRESS_BAR_HEIGHT) // 2
    canvas.alpha_composite(PIN_ICON, (left_x, left_top_y + (name_h - PIN_SIZE) // 2))
    draw.text(
        (left_x + PIN_SIZE + NAME_GAP, left_top_y + name_h // 2),
        item.area.name,
        font=name_font,
        fill=COLOR_NAME_PINK,
        anchor="lm",
    )
    progress_y = left_top_y + name_h + round(3 * SCALE)
    ratio = (item.area.progress / item.area.total) if item.area.total else 0
    _draw_progress_bar(canvas, (left_x, progress_y), left_w, ratio)

    # 子项区：地图游记 标题 + 3 列 grid
    sub_y = inner_y + item.banner_h + SUB_HEADER_TOP
    sub_left = inner_x + CARD_PAD
    canvas.alpha_composite(BOOK_ICON, (sub_left, sub_y))
    draw.text(
        (sub_left + BOOK_SIZE + SUB_TITLE_GAP, sub_y + BOOK_SIZE // 2),
        "地图游记",
        font=sub_title_font,
        fill=COLOR_SUB_TITLE,
        anchor="lm",
    )
    grid_y = sub_y + SUB_TITLE_BLOCK_H + SUB_GRID_TOP
    for idx, (sub, icon) in enumerate(item.rows):
        col = idx % 3
        row = idx // 3
        cell_x = sub_left + col * (SUB_CELL_W + GRID_COL_GAP)
        cell_y = grid_y + row * (SUB_CELL_H + SUB_ROW_GAP)
        _draw_sub_cell(canvas, draw, sub, icon, (cell_x, cell_y))

    return y + card_h


async def _prepare(area: AreaProgress) -> PreparedArea:
    banner = await _load_area_banner(area.id, CARD_INNER_W)
    rows = [(sub, await _load_sub_icon(sub.id)) for sub in area.detail]
    return PreparedArea(area=area, banner=banner, rows=rows, banner_h=_banner_total_height(banner.height))


async def draw_explore_img(ev: Event, areas: list[AreaProgress], role_name: str):
    prepared = [await _prepare(a) for a in areas]
    user_avatar = await get_event_avatar(ev)
    avatar_block = make_head_avatar(user_avatar, size=AVATAR_SIZE, avatar_size=AVATAR_INNER)

    body_h = sum(_card_height(len(p.rows), p.banner_h) for p in prepared) + max(0, len(prepared) - 1) * CARD_GAP
    body_top = AVATAR_Y + AVATAR_SIZE + BODY_TOP_GAP
    total_height = body_top + body_h + FOOTER_RESERVE

    canvas = get_nte_bg(WIDTH, total_height).convert("RGBA")
    canvas.paste(get_nte_title_bg(WIDTH, HEADER_HEIGHT), (0, 0))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEADER_HEIGHT), COLOR_OVERLAY), (0, 0))

    draw = ImageDraw.Draw(canvas)
    title_right = WIDTH - PADDING
    draw.text((title_right, 34), "异环·探索详情", font=nte_font_42, fill=COLOR_WHITE, anchor="ra")
    draw.text((title_right, 96), role_name, font=nte_font_30, fill=COLOR_SUBTEXT, anchor="ra")

    canvas.alpha_composite(avatar_block, (AVATAR_X, AVATAR_Y))

    y = body_top
    for index, item in enumerate(prepared):
        if index > 0:
            y += CARD_GAP
        y = _draw_card(canvas, draw, item, y)

    add_footer(canvas)
    return await convert_img(canvas)
