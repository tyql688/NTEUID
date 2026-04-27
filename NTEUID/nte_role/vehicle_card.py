from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    vw,
    add_footer,
    get_nte_bg,
    open_texture,
    rounded_mask,
    make_nte_role_title,
)
from ..utils.resource.cdn import get_vehicle_wide_img, get_vehicle_model_img
from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.sdk.tajiduo_model import Vehicle, VehicleList, VehicleBaseStat, VehicleAdvancedStat

WIDTH = 1080
FOOTER_RESERVE = 80

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "vehicle"
PAGE_PAD_X = vw(15)
CONTENT_WIDTH = WIDTH - PAGE_PAD_X * 2

CARD_RADIUS = vw(8)
CARD_GAP = vw(15)
CARD_PAD = vw(10)

VEHICLE_IMG_W = CONTENT_WIDTH - CARD_PAD * 2
VEHICLE_IMG_H_RATIO = 0.42
NAME_FONT = vw(18)
ID_FONT = vw(11)
NAME_GAP_X = vw(8)
HEADER_PAD_Y = vw(8)

SEC_ICON_SIZE = vw(16)
SEC_TITLE_FONT = vw(14)
SEC_TITLE_GAP = vw(3)
SEC_BLOCK_TOP = vw(10)
SEC_BLOCK_INNER_PAD = vw(11)
SEC_BLOCK_RADIUS = vw(8)
COLOR_SEC_BLOCK_BG = (54, 56, 58, 255)

PROP_LABEL_FONT = vw(11)
PROP_VALUE_FONT = vw(14)
PROP_ROW_GAP = vw(8)
BAR_W = vw(120)
BAR_H = vw(8)
BAR_BG_COLOR = (60, 60, 64, 255)
BAR_FILL_COLOR = (255, 174, 92, 255)
BAR_DOT_SIZE = vw(14)
BAR_DOT_COLOR = (255, 200, 120, 255)

MODEL_CELL_W = vw(50)
MODEL_CELL_H = vw(50)
MODEL_INNER_W = vw(46)
MODEL_GAP = vw(5)
MODEL_COLS = 6

LOGO_W = vw(88)
LOGO_PAD_Y = vw(8)

COLOR_CARD_BG = (38, 38, 40, 255)
COLOR_NAME = (255, 174, 92)
COLOR_ID = (170, 170, 170)
COLOR_LABEL = (220, 220, 220)
COLOR_VALUE = COLOR_WHITE
COLOR_SEC_TITLE = (229, 229, 229)
COLOR_LOCK_BG = (40, 40, 44, 220)
COLOR_LOCK_TEXT = (185, 185, 185)

name_font = nte_font_origin(NAME_FONT)
id_font = nte_font_origin(ID_FONT)
sec_title_font = nte_font_origin(SEC_TITLE_FONT)
prop_label_font = nte_font_origin(PROP_LABEL_FONT)
prop_value_font = nte_font_origin(PROP_VALUE_FONT)


SEC_ICON = open_texture(TEXTURE_PATH / "improve_icon.png", (SEC_ICON_SIZE, SEC_ICON_SIZE))
MODEL_BG = open_texture(TEXTURE_PATH / "model_bg.png", (MODEL_CELL_W, MODEL_CELL_H))
_LOGO = open_texture(TEXTURE_PATH / "bottom_logo.png")
LOGO = _LOGO.resize((LOGO_W, round(LOGO_W * _LOGO.height / _LOGO.width)), Image.Resampling.LANCZOS)


@dataclass(slots=True)
class PreparedVehicle:
    vehicle: Vehicle
    image: Image.Image | None
    models: list[Image.Image | None]


async def _prepare(vehicle: Vehicle) -> PreparedVehicle:
    image = await get_vehicle_wide_img(vehicle.id)
    models: list[Image.Image | None] = []
    for m in vehicle.models:
        models.append(await get_vehicle_model_img(m.type))
    return PreparedVehicle(vehicle, image, models)


def _vehicle_image_h(vehicle_img: Image.Image | None) -> int:
    if vehicle_img is None:
        return round(VEHICLE_IMG_W * VEHICLE_IMG_H_RATIO)
    return round(vehicle_img.height * VEHICLE_IMG_W / vehicle_img.width)


def _section_block_height(content_h: int) -> int:
    return max(SEC_ICON_SIZE, int(sec_title_font.size)) + SEC_TITLE_GAP + content_h + SEC_BLOCK_INNER_PAD * 2


def _base_block_height() -> int:
    return _section_block_height(int(prop_value_font.size) + PROP_ROW_GAP // 2 + int(prop_label_font.size))


def _advanced_block_height(adv_count: int) -> int:
    row_h = max(BAR_DOT_SIZE, int(prop_value_font.size))
    return _section_block_height(adv_count * row_h + max(0, adv_count - 1) * PROP_ROW_GAP)


def _models_block_height(model_count: int) -> int:
    rows = (model_count + MODEL_COLS - 1) // MODEL_COLS or 1
    return _section_block_height(rows * MODEL_CELL_H + max(0, rows - 1) * MODEL_GAP)


def _card_height(prepared: PreparedVehicle) -> int:
    image_h = _vehicle_image_h(prepared.image)
    height = CARD_PAD + image_h + HEADER_PAD_Y + max(int(name_font.size), int(id_font.size)) + HEADER_PAD_Y
    if prepared.vehicle.own:
        height += SEC_BLOCK_TOP + _base_block_height()
        height += SEC_BLOCK_TOP + _advanced_block_height(len(prepared.vehicle.advanced))
        if prepared.vehicle.models:
            height += SEC_BLOCK_TOP + _models_block_height(len(prepared.vehicle.models))
        height += LOGO_PAD_Y + LOGO.height + LOGO_PAD_Y
    else:
        height += SEC_BLOCK_TOP + vw(40)  # 「未拥有」chip 区
    return height + CARD_PAD


def _draw_section_title(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    title: str,
    xy: tuple[int, int],
) -> int:
    x, y = xy
    canvas.alpha_composite(SEC_ICON, (x, y))
    draw.text(
        (x + SEC_ICON_SIZE + SEC_TITLE_GAP, y + SEC_ICON_SIZE // 2),
        title,
        font=sec_title_font,
        fill=COLOR_SEC_TITLE,
        anchor="lm",
    )
    return y + max(SEC_ICON_SIZE, int(sec_title_font.size)) + SEC_TITLE_GAP


def _draw_section_block(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    title: str,
    xy: tuple[int, int],
    inner_h: int,
) -> tuple[int, int, int]:
    """画分节块：标题 + 圆角内容区。返回 (内容左 x, 内容顶 y, 内容宽 w)。"""
    x, y = xy
    title_bottom = _draw_section_title(canvas, draw, title, (x, y))
    block_top = title_bottom
    block_w = CONTENT_WIDTH - CARD_PAD * 2
    block_h = inner_h + SEC_BLOCK_INNER_PAD * 2
    bg = Image.new("RGBA", (block_w, block_h), COLOR_SEC_BLOCK_BG)
    canvas.paste(bg, (x, block_top), rounded_mask((block_w, block_h), SEC_BLOCK_RADIUS))
    return x + SEC_BLOCK_INNER_PAD, block_top + SEC_BLOCK_INNER_PAD, block_w - SEC_BLOCK_INNER_PAD * 2


def _draw_base_props(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    base: list[VehicleBaseStat],
    xy: tuple[int, int],
) -> int:
    inner_h = int(prop_value_font.size) + PROP_ROW_GAP // 2 + int(prop_label_font.size)
    inner_x, inner_y, inner_w = _draw_section_block(canvas, draw, "基础属性", xy, inner_h)
    if not base:
        return xy[1] + _section_block_height(inner_h)
    cols = len(base)
    cell_w = inner_w // cols
    for idx, stat in enumerate(base):
        cx = inner_x + cell_w * idx + cell_w // 2
        draw.text((cx, inner_y), stat.value, font=prop_value_font, fill=COLOR_VALUE, anchor="mt")
        draw.text(
            (cx, inner_y + int(prop_value_font.size) + PROP_ROW_GAP // 2),
            stat.name,
            font=prop_label_font,
            fill=COLOR_LABEL,
            anchor="mt",
        )
    return xy[1] + _section_block_height(inner_h)


def _draw_progress_bar(
    canvas: Image.Image,
    xy: tuple[int, int],
    ratio: float,
) -> None:
    x, y = xy
    bg = Image.new("RGBA", (BAR_W, BAR_H), BAR_BG_COLOR)
    canvas.paste(bg, (x, y), rounded_mask((BAR_W, BAR_H), BAR_H // 2))
    fill_w = max(0, min(BAR_W, round(BAR_W * min(ratio, 1.0))))
    if fill_w > 0:
        fill = Image.new("RGBA", (fill_w, BAR_H), BAR_FILL_COLOR)
        canvas.paste(fill, (x, y), rounded_mask((fill_w, BAR_H), BAR_H // 2))
    # 端点圆点
    dot_x = x + fill_w - BAR_DOT_SIZE // 2
    dot_y = y + BAR_H // 2 - BAR_DOT_SIZE // 2
    dot = Image.new("RGBA", (BAR_DOT_SIZE, BAR_DOT_SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(dot).ellipse((0, 0, BAR_DOT_SIZE - 1, BAR_DOT_SIZE - 1), fill=BAR_DOT_COLOR)
    canvas.alpha_composite(dot, (dot_x, dot_y))


def _draw_advanced_props(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    adv: list[VehicleAdvancedStat],
    xy: tuple[int, int],
) -> int:
    inner_h = len(adv) * max(BAR_DOT_SIZE, int(prop_value_font.size)) + max(0, len(adv) - 1) * PROP_ROW_GAP
    inner_x, inner_y, inner_w = _draw_section_block(canvas, draw, "改装属性", xy, inner_h)
    label_w = vw(70)
    value_w = vw(50)
    bar_x = inner_x + label_w
    row_h = max(BAR_DOT_SIZE, int(prop_value_font.size))
    for idx, stat in enumerate(adv):
        row_y = inner_y + idx * (row_h + PROP_ROW_GAP)
        cy = row_y + row_h // 2
        draw.text((inner_x, cy), stat.name, font=prop_label_font, fill=COLOR_LABEL, anchor="lm")
        try:
            cur = float(stat.value)
            mx = float(stat.max) if stat.max else 1.0
            ratio = cur / mx if mx else 0
        except ValueError:
            ratio = 0
        _draw_progress_bar(canvas, (bar_x, cy - BAR_H // 2), ratio)
        draw.text(
            (inner_x + inner_w - value_w + value_w // 2, cy),
            f"{stat.value}/{stat.max}",
            font=prop_value_font,
            fill=COLOR_VALUE,
            anchor="mm",
        )
    return xy[1] + _section_block_height(inner_h)


def _draw_models(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    models: list[Image.Image | None],
    xy: tuple[int, int],
) -> int:
    rows = (len(models) + MODEL_COLS - 1) // MODEL_COLS or 1
    inner_h = rows * MODEL_CELL_H + max(0, rows - 1) * MODEL_GAP
    inner_x, inner_y, inner_w = _draw_section_block(canvas, draw, "改装件", xy, inner_h)
    col_gap = max(MODEL_GAP, (inner_w - MODEL_CELL_W * MODEL_COLS) // max(1, MODEL_COLS - 1))
    for idx, img in enumerate(models):
        col = idx % MODEL_COLS
        row = idx // MODEL_COLS
        cell_x = inner_x + col * (MODEL_CELL_W + col_gap)
        cell_y = inner_y + row * (MODEL_CELL_H + MODEL_GAP)
        canvas.alpha_composite(MODEL_BG, (cell_x, cell_y))
        if img is not None:
            fitted = ImageOps.fit(img, (MODEL_INNER_W, MODEL_INNER_W), Image.Resampling.LANCZOS)
            offset = (MODEL_CELL_W - MODEL_INNER_W) // 2
            canvas.alpha_composite(fitted, (cell_x + offset, cell_y + offset))
    return xy[1] + _section_block_height(inner_h)


def _draw_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    prepared: PreparedVehicle,
    y: int,
) -> int:
    card_x = PAGE_PAD_X
    card_h = _card_height(prepared)
    bg_layer = Image.new("RGBA", (CONTENT_WIDTH, card_h), COLOR_CARD_BG)
    canvas.paste(bg_layer, (card_x, y), rounded_mask((CONTENT_WIDTH, card_h), CARD_RADIUS))

    inner_x = card_x + CARD_PAD
    cur_y = y + CARD_PAD

    # 顶部车辆图
    image_h = _vehicle_image_h(prepared.image)
    if prepared.image is not None:
        fitted = ImageOps.fit(prepared.image, (VEHICLE_IMG_W, image_h), Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        canvas.paste(fitted, (inner_x, cur_y), rounded_mask((VEHICLE_IMG_W, image_h), CARD_RADIUS))
    else:
        draw.rounded_rectangle(
            (inner_x, cur_y, inner_x + VEHICLE_IMG_W, cur_y + image_h),
            radius=CARD_RADIUS,
            fill=(60, 60, 64, 255),
        )
    cur_y += image_h + HEADER_PAD_Y

    # 名称行
    draw.text((inner_x, cur_y), prepared.vehicle.name, font=name_font, fill=COLOR_NAME, anchor="lt")
    name_w = draw.textlength(prepared.vehicle.name, font=name_font)
    draw.text(
        (inner_x + name_w + NAME_GAP_X, cur_y + int(name_font.size) - int(id_font.size)),
        f"#{prepared.vehicle.id}",
        font=id_font,
        fill=COLOR_ID,
        anchor="lt",
    )
    cur_y += max(int(name_font.size), int(id_font.size)) + HEADER_PAD_Y

    if not prepared.vehicle.own:
        cur_y += SEC_BLOCK_TOP
        chip_h = vw(40)
        bg = Image.new("RGBA", (VEHICLE_IMG_W, chip_h), COLOR_LOCK_BG)
        canvas.paste(bg, (inner_x, cur_y), rounded_mask((VEHICLE_IMG_W, chip_h), SEC_BLOCK_RADIUS))
        draw.text(
            (inner_x + VEHICLE_IMG_W // 2, cur_y + chip_h // 2),
            "未拥有",
            font=sec_title_font,
            fill=COLOR_LOCK_TEXT,
            anchor="mm",
        )
        return y + card_h

    cur_y += SEC_BLOCK_TOP
    cur_y = _draw_base_props(canvas, draw, prepared.vehicle.base, (inner_x, cur_y))
    cur_y += SEC_BLOCK_TOP
    cur_y = _draw_advanced_props(canvas, draw, prepared.vehicle.advanced, (inner_x, cur_y))
    if prepared.vehicle.models:
        cur_y += SEC_BLOCK_TOP
        cur_y = _draw_models(canvas, draw, prepared.models, (inner_x, cur_y))

    # 底部 logo
    logo_y = cur_y + LOGO_PAD_Y
    canvas.alpha_composite(LOGO, (card_x + CONTENT_WIDTH - CARD_PAD - LOGO.width, logo_y))
    return y + card_h


async def draw_vehicle_img(ev: Event, vehicles: VehicleList, role_name: str, uid: str):
    prepared = [await _prepare(v) for v in vehicles.detail if v.own]
    user_avatar = await get_event_avatar(ev)

    body_top = 258
    body_h = sum(_card_height(p) for p in prepared) + max(0, len(prepared) - 1) * CARD_GAP
    total_height = body_top + body_h + FOOTER_RESERVE

    canvas = get_nte_bg(WIDTH, total_height).convert("RGBA")
    title = make_nte_role_title(user_avatar, role_name, uid).resize((1024, 201), Image.Resampling.LANCZOS)
    canvas.alpha_composite(title, (36, 30))

    draw = ImageDraw.Draw(canvas)

    y = body_top
    for index, prep in enumerate(prepared):
        if index > 0:
            y += CARD_GAP
        y = _draw_card(canvas, draw, prep, y)

    add_footer(canvas)
    return await convert_img(canvas)
