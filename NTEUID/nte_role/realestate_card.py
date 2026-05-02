from __future__ import annotations

import json
from pathlib import Path
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    vw,
    add_footer,
    get_nte_bg,
    open_texture,
    rounded_mask,
    char_img_ring,
    make_nte_role_title,
)
from ..utils.resource.cdn import (
    get_avatar_img,
    get_furniture_img,
    get_realestate_img,
)
from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.sdk.tajiduo_model import House, Furniture

WIDTH = 1080
FOOTER_RESERVE = 80

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "realestate"
PAGE_PAD_X = vw(15)
CONTENT_WIDTH = WIDTH - PAGE_PAD_X * 2

CARD_RADIUS = vw(6)
CARD_GAP = vw(15)
CARD_PAD_X = vw(8)
CARD_PAD_Y = vw(8)
HEADER_ROW_TOP = vw(5)
HEADER_ROW_INSET = vw(5)
PIN_SIZE = vw(16)
NAME_GAP = vw(5)
NAME_FONT = vw(15)
BODY_TOP_PAD = vw(5)
BODY_INSET_X = vw(10)
BODY_INSET_Y = vw(8)
HOUSE_IMG_W = vw(198)
HOUSE_IMG_H = vw(133)
CHARS_BLOCK_LEFT = vw(10)
CHARS_BLOCK_W = vw(140)
CHARS_TOP_OFFSET = vw(38)
CHIP_H = vw(16)
CHIP_FONT = vw(10)
CHAR_BG_SIZE = vw(37)
CHAR_AVATAR_SIZE = vw(30)
CHARS_GRID_GAP = vw(3)
CHARS_GRID_TOP = vw(3)

SEC_ICON_SIZE = vw(16)
SEC_TITLE_FONT = vw(14)
SEC_TITLE_GAP = vw(5)
SEC_TOP = vw(5)
GRID_INNER_PAD_X = vw(7)
GRID_INNER_PAD_Y = vw(7)
GRID_GAP = vw(5)
GRID_RADIUS = vw(6)
FURN_BG_SIZE = vw(62)
FURN_INNER_SIZE = vw(47)
FURN_LOCK_SIZE = vw(62)
FURN_LOCK_FONT = vw(9)
LOGO_W = vw(97)
LOGO_PAD_Y = vw(8)

COLOR_CARD_BG = (48, 48, 50, 255)
COLOR_NAME = (231, 108, 13)
COLOR_CHIP_BG = (70, 70, 70)
COLOR_CHIP_TEXT = (241, 241, 241)
COLOR_SEC_TITLE = (229, 229, 229)
COLOR_FURN_LOCK_TEXT = (195, 195, 195)
COLOR_GRID_BG = (0, 0, 0, 255)

name_font = nte_font_origin(NAME_FONT)
chip_font = nte_font_origin(CHIP_FONT)
sec_title_font = nte_font_origin(SEC_TITLE_FONT)
furn_lock_font = nte_font_origin(FURN_LOCK_FONT)


PIN_ICON = open_texture(TEXTURE_PATH / "pin.png", (PIN_SIZE, PIN_SIZE))
SEC_ICON = open_texture(TEXTURE_PATH / "sec_icon.png", (SEC_ICON_SIZE, SEC_ICON_SIZE))
FURN_EMPTY_BG = open_texture(TEXTURE_PATH / "furniture_empty.png", (FURN_BG_SIZE, FURN_BG_SIZE))
UNLOCK_MASK = open_texture(TEXTURE_PATH / "unlock_mask.png", (FURN_LOCK_SIZE, FURN_LOCK_SIZE))
LOGO = open_texture(TEXTURE_PATH / "logo.png")
LOGO_RESIZED = LOGO.resize((LOGO_W, round(LOGO_W * LOGO.height / LOGO.width)), Image.Resampling.LANCZOS)


@dataclass(slots=True)
class PreparedHouse:
    house: House
    house_img: Image.Image | None
    char_avatars: list[Image.Image]
    furnitures: list[tuple[Furniture, Image.Image | None]]


async def _prepare(house: House) -> PreparedHouse:
    house_img = await get_realestate_img(house.id)
    char_avatars: list[Image.Image] = []
    if house.chars:
        try:
            char_ids = json.loads(house.chars)
        except json.JSONDecodeError:
            char_ids = []
        for cid in char_ids:
            img = await get_avatar_img(str(cid))
            if img is not None:
                fitted = ImageOps.fit(
                    img, (CHAR_AVATAR_SIZE, CHAR_AVATAR_SIZE), Image.Resampling.LANCZOS, centering=(0.5, 0.15)
                )
                char_avatars.append(fitted)
    furnitures: list[tuple[Furniture, Image.Image | None]] = []
    for f in house.fdetail:
        img = await get_furniture_img(f.id) if f.own else None
        if img is not None:
            img = ImageOps.fit(img, (FURN_INNER_SIZE, FURN_INNER_SIZE), Image.Resampling.LANCZOS)
        furnitures.append((f, img))
    return PreparedHouse(house, house_img, char_avatars, furnitures)


def _grid_rows(cnt: int, cols: int) -> int:
    return (cnt + cols - 1) // cols


def _card_height(prepared: PreparedHouse) -> int:
    body_h = max(HOUSE_IMG_H, CHARS_TOP_OFFSET + CHIP_H + CHARS_GRID_TOP + CHAR_BG_SIZE * 2 + CHARS_GRID_GAP)
    rows = _grid_rows(len(prepared.furnitures), 5) or 1
    grid_inner_h = rows * FURN_BG_SIZE + (rows - 1) * GRID_GAP
    grid_h = SEC_TOP + max(SEC_ICON_SIZE, int(sec_title_font.size)) + GRID_INNER_PAD_Y + grid_inner_h + GRID_INNER_PAD_Y
    return (
        CARD_PAD_Y
        + HEADER_ROW_TOP
        + max(PIN_SIZE, int(name_font.size))
        + BODY_TOP_PAD
        + body_h
        + grid_h
        + LOGO_RESIZED.height
        + LOGO_PAD_Y * 2
        + CARD_PAD_Y
    )


def _draw_chip(draw: ImageDraw.ImageDraw, xy: tuple[int, int], w: int, text: str) -> None:
    x, y = xy
    draw.rounded_rectangle((x, y, x + w, y + CHIP_H), radius=CHIP_H // 2, fill=COLOR_CHIP_BG)
    draw.text((x + w // 2, y + CHIP_H // 2), text, font=chip_font, fill=COLOR_CHIP_TEXT, anchor="mm")


def _draw_chars_grid(canvas: Image.Image, avatars: list[Image.Image], xy: tuple[int, int]) -> None:
    """每个角色：圆头像。3 列 grid。"""
    x, y = xy
    for idx, avatar in enumerate(avatars):
        col = idx % 3
        row = idx // 3
        cell_x = x + col * (CHAR_BG_SIZE + CHARS_GRID_GAP)
        cell_y = y + row * (CHAR_BG_SIZE + CHARS_GRID_GAP)
        cx = cell_x + CHAR_BG_SIZE // 2
        cy = cell_y + CHAR_BG_SIZE // 2
        avatar_x = cx - CHAR_AVATAR_SIZE // 2
        avatar_y = cy - CHAR_AVATAR_SIZE // 2
        canvas.alpha_composite(char_img_ring(avatar, CHAR_AVATAR_SIZE), (avatar_x, avatar_y))


def _draw_furniture_cell(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    image: Image.Image | None,
    xy: tuple[int, int],
) -> None:
    x, y = xy
    canvas.alpha_composite(FURN_EMPTY_BG, (x, y))
    if image is not None:
        center_x = x + FURN_BG_SIZE // 2 - FURN_INNER_SIZE // 2
        center_y = y + FURN_BG_SIZE // 2 - FURN_INNER_SIZE // 2
        canvas.alpha_composite(image, (center_x, center_y))
    else:
        # 未拥有：未解锁 mask + 标签
        canvas.alpha_composite(UNLOCK_MASK, (x, y))
        draw.text(
            (x + FURN_BG_SIZE // 2 + vw(5), y + FURN_BG_SIZE // 2),
            "未解锁",
            font=furn_lock_font,
            fill=COLOR_FURN_LOCK_TEXT,
            anchor="mm",
        )


def _draw_card(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    prepared: PreparedHouse,
    y: int,
) -> int:
    card_x = PAGE_PAD_X
    card_h = _card_height(prepared)
    bg_layer = Image.new("RGBA", (CONTENT_WIDTH, card_h), COLOR_CARD_BG)
    canvas.paste(bg_layer, (card_x, y), rounded_mask((CONTENT_WIDTH, card_h), CARD_RADIUS))

    inner_x = card_x + HEADER_ROW_INSET
    cur_y = y + CARD_PAD_Y + HEADER_ROW_TOP

    # 头部：pin + name + (location 备用)
    canvas.alpha_composite(PIN_ICON, (inner_x, cur_y + (max(PIN_SIZE, int(name_font.size)) - PIN_SIZE) // 2))
    name_x = inner_x + PIN_SIZE + NAME_GAP
    draw.text((name_x, cur_y), prepared.house.name, font=name_font, fill=COLOR_NAME, anchor="lt")
    cur_y += max(PIN_SIZE, int(name_font.size)) + BODY_TOP_PAD

    # 主体：左侧房屋图，右侧入住角色 chip + chars grid
    body_left = card_x + CARD_PAD_X
    body_inner_w = CONTENT_WIDTH - CARD_PAD_X * 2
    body_h = max(
        HOUSE_IMG_H,
        CHARS_TOP_OFFSET + CHIP_H + CHARS_GRID_TOP + CHAR_BG_SIZE * 2 + CHARS_GRID_GAP,
    )

    # 房屋图
    if prepared.house_img is not None:
        fitted = ImageOps.fit(
            prepared.house_img,
            (HOUSE_IMG_W, HOUSE_IMG_H),
            Image.Resampling.LANCZOS,
            centering=(0.5, 0.5),
        )
        canvas.paste(
            fitted,
            (body_left + BODY_INSET_X, cur_y + BODY_INSET_Y),
            rounded_mask((HOUSE_IMG_W, HOUSE_IMG_H), GRID_RADIUS),
        )
    else:
        draw.rounded_rectangle(
            (
                body_left + BODY_INSET_X,
                cur_y + BODY_INSET_Y,
                body_left + BODY_INSET_X + HOUSE_IMG_W,
                cur_y + BODY_INSET_Y + HOUSE_IMG_H,
            ),
            radius=GRID_RADIUS,
            fill=(80, 80, 80, 255),
        )

    # 入住角色 chip + chars
    chars_x = body_left + BODY_INSET_X + HOUSE_IMG_W + CHARS_BLOCK_LEFT
    chars_y = cur_y + BODY_INSET_Y + CHARS_TOP_OFFSET
    chip_w = min(CHARS_BLOCK_W, body_inner_w - (chars_x - body_left))
    _draw_chip(draw, (chars_x, chars_y), chip_w, "邀约入住")
    grid_y = chars_y + CHIP_H + CHARS_GRID_TOP
    _draw_chars_grid(canvas, prepared.char_avatars, (chars_x, grid_y))

    cur_y += body_h + CARD_PAD_Y

    # 异象家具 grid
    sec_x = card_x + CARD_PAD_X + vw(8)
    canvas.alpha_composite(SEC_ICON, (sec_x, cur_y))
    sec_text_x = sec_x + SEC_ICON_SIZE + SEC_TITLE_GAP
    draw.text(
        (sec_text_x, cur_y + SEC_ICON_SIZE // 2),
        "异象家具",
        font=sec_title_font,
        fill=COLOR_SEC_TITLE,
        anchor="lm",
    )
    cur_y += max(SEC_ICON_SIZE, int(sec_title_font.size)) + GRID_INNER_PAD_Y

    # grid 黑底
    grid_left = sec_x
    grid_right = card_x + CONTENT_WIDTH - CARD_PAD_X - vw(8)
    grid_w = grid_right - grid_left
    rows = _grid_rows(len(prepared.furnitures), 5) or 1
    grid_inner_h = rows * FURN_BG_SIZE + (rows - 1) * GRID_GAP
    grid_box_h = grid_inner_h + GRID_INNER_PAD_Y * 2
    bg = Image.new("RGBA", (grid_w, grid_box_h), COLOR_GRID_BG)
    canvas.paste(bg, (grid_left, cur_y), rounded_mask((grid_w, grid_box_h), GRID_RADIUS))

    # 5 列均布
    inner_grid_w = grid_w - GRID_INNER_PAD_X * 2
    col_gap = (inner_grid_w - FURN_BG_SIZE * 5) // 4 if inner_grid_w > FURN_BG_SIZE * 5 else GRID_GAP
    for idx, (_furn, image) in enumerate(prepared.furnitures):
        col = idx % 5
        row = idx // 5
        cell_x = grid_left + GRID_INNER_PAD_X + col * (FURN_BG_SIZE + col_gap)
        cell_y = cur_y + GRID_INNER_PAD_Y + row * (FURN_BG_SIZE + GRID_GAP)
        _draw_furniture_cell(canvas, draw, image, (cell_x, cell_y))

    cur_y += grid_box_h
    # 底部 logo（右下）
    logo_y = cur_y + LOGO_PAD_Y
    canvas.alpha_composite(LOGO_RESIZED, (grid_right - LOGO_RESIZED.width, logo_y))

    return y + card_h


async def draw_realestate_img(ev: Event, houses: list[House], role_name: str, uid: str):
    prepared = [await _prepare(h) for h in houses]
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
