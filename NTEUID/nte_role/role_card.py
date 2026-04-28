from __future__ import annotations

import random
from pathlib import Path
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from .role_sort import sort_characters
from ..utils.image import (
    add_footer,
    get_nte_bg,
    make_head_avatar,
)
from ..utils.resource.cdn import (
    get_area_wide_img,
    get_char_group_img,
    get_char_detail_img,
    get_char_element_img,
)
from ..utils.fonts.nte_fonts import (
    nte_font_22,
    nte_font_26,
    nte_font_30,
    nte_font_36,
    nte_font_42,
    nte_font_50,
)
from ..utils.sdk.tajiduo_model import (
    RoleHome,
    CharElement,
    CharQuality,
    CharacterDetail,
    RoleHomeAreaProgress,
)

TEXTURE_PATH = Path(__file__).parent / "texture2d"
CARD_TEX_PATH = TEXTURE_PATH / "card"
CARD_BG_DIR = CARD_TEX_PATH / "bg_card"

WIDTH = 1080

SECTION_GAP = 32
GRID_GAP = 18
PADDING = 40
HEADER_HEIGHT = int(WIDTH / 870 * 723)

SECTION_TITLE_HEIGHT = 78
AREA_COLS = 4
AREA_CARD_HEIGHT = 330
CHAR_COLS = 4
CHAR_CARD_HEIGHT = 380

COLOR_TEXT = (240, 240, 245)
COLOR_MUTED = (160, 160, 175)
COLOR_ACCENT = (236, 64, 122)
COLOR_ACCENT_SOFT = (255, 95, 150)

_CARD_BG_FILES = ("card_1.png", "card_2.png", "card_3.png")


@dataclass(slots=True)
class _CharStat:
    level: int
    awaken: int
    quality: CharQuality
    element: CharElement
    avatar: Image.Image | None
    element_icon: Image.Image | None
    group_icon: Image.Image | None


def _pick_area_bg(index: int) -> Image.Image:
    name = _CARD_BG_FILES[index % len(_CARD_BG_FILES)]
    return Image.open(CARD_BG_DIR / name).convert("RGBA")


def _load_char_bg(quality: CharQuality) -> Image.Image:
    return Image.open(CARD_TEX_PATH / f"char_{quality.letter}_bg.png").convert("RGBA")


def _draw_section_title(canvas: Image.Image, y: int, title: str, align: str = "left") -> int:
    banner = Image.open(CARD_TEX_PATH / "banner.png").convert("RGBA")
    banner_x = canvas.width - PADDING - banner.width if align == "right" else PADDING
    canvas.alpha_composite(banner, (banner_x, y))
    text_x = banner_x + 78 + (banner.width - 78 - 6) // 2 - 15
    text_y = y + banner.height // 2
    draw = ImageDraw.Draw(canvas)
    draw.text((text_x, text_y), title, font=nte_font_30, fill=(0, 0, 0), anchor="mm")
    return y + SECTION_TITLE_HEIGHT


def _draw_header(
    canvas: Image.Image,
    home: RoleHome,
    role_name: str,
    user_avatar: Image.Image,
) -> None:
    bg = _pick_area_bg(random.randrange(len(_CARD_BG_FILES))).resize(
        (canvas.width, HEADER_HEIGHT), Image.Resampling.LANCZOS
    )
    canvas.alpha_composite(bg, (0, 0))

    canvas.alpha_composite(make_head_avatar(user_avatar), (18, 400))

    draw = ImageDraw.Draw(canvas)
    draw.text((280, 555), role_name, font=nte_font_42, fill=COLOR_TEXT, anchor="lm")
    draw.text((295, 608), f"UID {home.role_id}", font=nte_font_30, fill=(0, 0, 0), anchor="lm")

    level_img = Image.open(CARD_TEX_PATH / "level.png").convert("RGBA")
    lv_cx, lv_cy = 990, 588
    canvas.alpha_composite(level_img, (lv_cx - level_img.width // 2, lv_cy - level_img.height // 2))
    draw.text((lv_cx, lv_cy), str(home.lev), font=nte_font_42, fill=COLOR_TEXT, anchor="mm")

    # 活跃天数：right-aligned 贴在 level 圆章左侧，数字大号 + 标签小号 + 一道分隔竖线作装饰
    sep_x = lv_cx - level_img.width // 2 - 12
    draw.line([(sep_x, lv_cy - 36), (sep_x, lv_cy + 36)], fill=COLOR_ACCENT, width=2)
    days_right = sep_x - 18
    days_y = lv_cy + 14
    draw.text(
        (days_right, days_y - 4), str(home.role_login_days), font=nte_font_50, fill=COLOR_ACCENT_SOFT, anchor="rb"
    )
    draw.text((days_right, days_y + 4), "活跃天数", font=nte_font_22, fill=COLOR_TEXT, anchor="rt")


def _draw_stats(canvas: Image.Image, y: int, home: RoleHome) -> int:
    achieve_cnt = home.achieve_progress.achievement_cnt if home.achieve_progress else 0
    vehicle_own = home.vehicle.own_cnt if home.vehicle else 0
    realestate_own = home.realestate.own_cnt if home.realestate else 0
    cells = [
        (str(achieve_cnt), "达成成就"),
        (str(home.tycoon_level), "大亨等级"),
        (str(realestate_own), "房产数量"),
        (str(vehicle_own), "载具数量"),
    ]
    # 数字黑压 card_1.png 白条上半，标签白压 stats.png 深条下半
    chip = Image.open(CARD_TEX_PATH / "stats.png").convert("RGBA")
    chip_w, chip_h = chip.size
    start_x = 150
    chip_gap = 55
    draw = ImageDraw.Draw(canvas)
    for index, (value, label) in enumerate(cells):
        left = start_x + index * (chip_w + chip_gap)
        cx = left + chip_w // 2
        canvas.alpha_composite(chip, (left, y))
        draw.text((cx, y + 15), value, font=nte_font_50, fill=(0, 0, 0), anchor="mm")
        draw.text((cx, y + 70), label, font=nte_font_30, fill=COLOR_TEXT, anchor="mm")
    return y + chip_h


async def _draw_area_cards(canvas: Image.Image, y: int, areas: list[RoleHomeAreaProgress]) -> int:
    if not areas:
        return y
    inner = canvas.width - PADDING * 2
    card_w = (inner - GRID_GAP * (AREA_COLS - 1)) // AREA_COLS
    card_h = AREA_CARD_HEIGHT
    rows = (len(areas) + AREA_COLS - 1) // AREA_COLS

    exp_bg_raw = Image.open(CARD_TEX_PATH / "exp_bg.png").convert("RGBA")
    exp_mask = Image.open(CARD_TEX_PATH / "exp_mask.png")

    draw = ImageDraw.Draw(canvas)
    for index, area in enumerate(areas):
        row, col = divmod(index, AREA_COLS)
        card_x = PADDING + col * (card_w + GRID_GAP)
        card_y = y + row * (card_h + GRID_GAP)

        # 套路：mask/bg 都用原生尺寸，组装完再 resize 到 card slot
        mine_bg = exp_bg_raw.copy()
        area_raw = await get_area_wide_img(area.id)
        if area_raw is not None:
            temp_bg = Image.new("RGBA", exp_mask.size)
            temp_bg2 = Image.new("RGBA", exp_mask.size)
            area_img = ImageOps.fit(area_raw, exp_mask.size, Image.Resampling.LANCZOS)
            temp_bg.alpha_composite(area_img, (0, 0))
            temp_bg2.paste(temp_bg, (0, 0), exp_mask)
            mine_bg.alpha_composite(temp_bg2, (0, 0))

        canvas.alpha_composite(mine_bg.resize((card_w, card_h), Image.Resampling.LANCZOS), (card_x, card_y))

        percent = f"{min(round(area.progress / area.total * 100), 100)}%" if area.total else "--%"
        draw.text((card_x + card_w // 2, card_y + card_h - 65), percent, font=nte_font_30, fill=(0, 0, 0), anchor="mm")
        draw.text(
            (card_x + card_w // 2, card_y + card_h - 30), area.name, font=nte_font_36, fill=COLOR_MUTED, anchor="mm"
        )

    return y + rows * card_h + (rows - 1) * GRID_GAP


async def _build_char_stats(
    home: RoleHome,
    characters: list[CharacterDetail],
) -> list[_CharStat]:
    source = sort_characters(characters) if characters else home.characters
    result: list[_CharStat] = []
    for item in source:
        result.append(
            _CharStat(
                level=item.alev,
                awaken=item.awaken_lev,
                quality=item.quality,
                element=item.element_type,
                avatar=await get_char_detail_img(item.id),
                element_icon=await get_char_element_img(item.element_type.value),
                group_icon=await get_char_group_img(item.group_type.value),
            )
        )
    return result


def _draw_char_grid(canvas: Image.Image, y: int, chars: list[_CharStat]) -> int:
    if not chars:
        return y

    inner = canvas.width - PADDING * 2
    card_w = (inner - GRID_GAP * (CHAR_COLS - 1)) // CHAR_COLS
    card_h = CHAR_CARD_HEIGHT
    rows = (len(chars) + CHAR_COLS - 1) // CHAR_COLS
    mask = Image.open(CARD_TEX_PATH / "char_mask.png")
    ring = Image.open(CARD_TEX_PATH / "char_ring.png").convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    for index, char in enumerate(chars):
        row, col = divmod(index, CHAR_COLS)
        cx = PADDING + col * (card_w + GRID_GAP)
        cy = y + row * (card_h + GRID_GAP)

        # 套路：所有操作都在 mask/bg 原生尺寸上，mask 不 resize
        mine_bg = _load_char_bg(char.quality).copy()
        if char.avatar is not None:
            temp_bg = Image.new("RGBA", mask.size)
            temp_bg2 = Image.new("RGBA", mask.size)
            avatar = ImageOps.fit(char.avatar.convert("RGBA"), mask.size, Image.Resampling.LANCZOS)
            temp_bg.alpha_composite(avatar, (-10, 0))
            temp_bg2.paste(temp_bg, (0, 0), mask)
            mine_bg.alpha_composite(temp_bg2, (0, 0))
        # 组装完再整体缩放到 grid 里 card slot 的显示尺寸
        canvas.alpha_composite(mine_bg.resize((card_w, card_h), Image.Resampling.LANCZOS), (cx, cy))

        # 属性徽章：char_ring 作底 + 属性图标，左上
        if char.element_icon is not None:
            ex, ey = cx + 15, cy + 18
            canvas.alpha_composite(ring, (ex, ey))
            canvas.alpha_composite(
                char.element_icon.resize((ring.width, ring.height), Image.Resampling.LANCZOS), (ex, ey)
            )

        # 阵营徽章：属性下方，同样 ring + 图标
        if char.group_icon is not None:
            gx, gy = cx + 15, cy + 18 + ring.height + 8
            canvas.alpha_composite(ring, (gx, gy))
            canvas.alpha_composite(
                char.group_icon.resize((ring.width, ring.height), Image.Resampling.LANCZOS), (gx, gy)
            )

        # 觉醒徽章：卡进 S 质量三角形的右上角
        if char.awaken:
            ax, ay = cx + card_w - ring.width - 15, cy + card_h - ring.height - 160
            canvas.alpha_composite(ring, (ax, ay))
            draw.text(
                (ax + ring.width // 2, ay + ring.height // 2),
                str(char.awaken),
                font=nte_font_22,
                fill=COLOR_TEXT,
                anchor="mm",
            )

        draw.text((cx + 24, cy + card_h - 64), f"LV{char.level}", font=nte_font_26, fill=COLOR_TEXT)

    return y + rows * card_h + (rows - 1) * GRID_GAP


async def draw_role_card_img(
    ev: Event,
    home: RoleHome,
    characters: list[CharacterDetail],
    role_name: str,
):
    chars = await _build_char_stats(home, characters)
    char_rows = max(1, (len(chars) + CHAR_COLS - 1) // CHAR_COLS)
    area_rows = max(1, (len(home.area_progress) + AREA_COLS - 1) // AREA_COLS)
    canvas_height = (
        HEADER_HEIGHT
        + SECTION_TITLE_HEIGHT
        + area_rows * AREA_CARD_HEIGHT
        + (area_rows - 1) * GRID_GAP
        + SECTION_GAP
        + SECTION_TITLE_HEIGHT
        + char_rows * CHAR_CARD_HEIGHT
        + (char_rows - 1) * GRID_GAP
        + SECTION_GAP
        + 80
    )
    canvas = get_nte_bg(WIDTH, canvas_height).convert("RGBA")

    user_avatar = await get_event_avatar(ev)
    _draw_header(canvas, home, role_name, user_avatar)
    # stats.png 贴到 header 内部的白条（card_1.png native y=528~650 → 缩放到 canvas y≈655~806）
    _draw_stats(canvas, 700, home)

    y = HEADER_HEIGHT
    y = _draw_section_title(canvas, y, "探索进度", align="right") + 12
    y = await _draw_area_cards(canvas, y, home.area_progress) + SECTION_GAP
    y = _draw_section_title(canvas, y, "角色列表") + 12
    y = _draw_char_grid(canvas, y, chars) + SECTION_GAP
    add_footer(canvas)

    return await convert_img(canvas)
