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
    rounded_mask,
    get_nte_title_bg,
    make_head_avatar,
)
from ..utils.resource.cdn import get_achievement_img
from ..utils.fonts.nte_fonts import nte_font_30, nte_font_42, nte_font_origin
from ..utils.sdk.tajiduo_model import AchievementCategory, AchievementProgress

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

SCALE = 1080 / 390


def vw(n: float) -> int:
    return round(n * SCALE)


# 外面板：bg-#EFEFEF 与角色详情统一
OUTER_RADIUS = vw(20)
OUTER_PAD_X = vw(15)
OUTER_PAD_Y = vw(20)

# 头部 banner（vj）：header_bg.png 全宽，覆盖文字 + 3 个 UMD 徽章
HEADER_TEXT_FONT = vw(15)
HEADER_TEXT_LABEL_FONT = vw(10)
HEADER_DIVIDER_W = vw(1)
HEADER_DIVIDER_H = vw(24)
HEADER_LEFT_PAD = vw(17)  # mx-vw-17
HEADER_TEXT_TOP = vw(5)  # top-vw-5

UMD_BADGE_W = vw(65)  # w-vw-65
UMD_NUM_FONT = vw(12)
UMD_NUM_OFFSET_X = vw(15)  # ml-vw-15
UMD_GAP = vw(6)  # gap-x-vw-6

# 类目项（gj）：item_bg.png 全宽，左 icon w-vw-64，名字 text-vw-18，右进度 text-vw-15
ITEM_GAP = vw(14)  # mt-vw-14 列表起始
ITEM_PAD_X = vw(8)  # mx-vw-8
ITEM_PAD_Y = vw(8)  # mt-vw-8
ITEM_ICON_W = vw(64)
ITEM_ICON_LEFT = vw(6)  # ml-vw-6
ITEM_NAME_FONT = vw(18)
ITEM_NAME_LEFT = vw(18)  # ml-vw-18 from icon left
ITEM_PROG_FONT = vw(15)

COLOR_OUTER = (239, 239, 239, 255)
COLOR_HEAD_NUM = (242, 255, 37)  # #F2FF25
COLOR_HEAD_LABEL = (206, 219, 0)  # #CEDB00
COLOR_HEAD_DIVIDER = (50, 50, 50)  # #323232
COLOR_UMD_NUM = (224, 224, 224)  # #E0E0E0
COLOR_ITEM_TEXT = (35, 35, 35)  # #232323

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "achievement"


def _load(name: str) -> Image.Image:
    return Image.open(TEXTURE_PATH / name).convert("RGBA")


HEADER_BG = _load("header_bg.png")
ITEM_BG = _load("item_bg.png")
UMD_GOLD = _load("umd_gold.png")
UMD_SILVER = _load("umd_silver.png")
UMD_COPPER = _load("umd_copper.png")

head_num_font = nte_font_origin(HEADER_TEXT_FONT)
head_label_font = nte_font_origin(HEADER_TEXT_LABEL_FONT)
umd_num_font = nte_font_origin(UMD_NUM_FONT)
item_name_font = nte_font_origin(ITEM_NAME_FONT)
item_prog_font = nte_font_origin(ITEM_PROG_FONT)


async def _safe(coro) -> Image.Image | None:
    try:
        return await coro
    except OSError:
        return None


def _scaled(img: Image.Image, target_w: int) -> Image.Image:
    new_h = round(img.height * target_w / img.width)
    return img.resize((target_w, new_h), Image.Resampling.LANCZOS)


def _draw_umd_badge(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, xy: tuple[int, int], badge: Image.Image, num: int
) -> int:
    """官方 Kf：徽章图 + 数字叠在徽章右半（ml-vw-15）。"""
    x, y = xy
    scaled = _scaled(badge, UMD_BADGE_W)
    canvas.alpha_composite(scaled, (x, y))
    draw.text(
        (x + UMD_NUM_OFFSET_X + (scaled.width - UMD_NUM_OFFSET_X) // 2, y + scaled.height // 2),
        str(num),
        font=umd_num_font,
        fill=COLOR_UMD_NUM,
        anchor="mm",
    )
    return scaled.width


def _draw_header(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    progress: AchievementProgress,
) -> int:
    """vj：header_bg 全宽 + 收集磁带数 + | + 3 个 UMD 徽章。"""
    x, y = xy
    bg = _scaled(HEADER_BG, width)
    canvas.alpha_composite(bg, (x, y))
    bg_h = bg.height

    inner_x = x + HEADER_LEFT_PAD
    text_top = y + HEADER_TEXT_TOP
    cy_band = y + bg_h // 2

    # 左：磁带数 + "收集磁带"
    num_text = str(progress.achievement_cnt)
    num_w = round(draw.textlength(num_text, font=head_num_font))
    label = "收集磁带"
    label_w = round(draw.textlength(label, font=head_label_font))
    block_w = max(num_w, label_w)
    block_cx = inner_x + block_w // 2
    draw.text((block_cx, text_top), num_text, font=head_num_font, fill=COLOR_HEAD_NUM, anchor="mt")
    draw.text(
        (block_cx, text_top + int(head_num_font.size) + vw(2)),
        label,
        font=head_label_font,
        fill=COLOR_HEAD_LABEL,
        anchor="mt",
    )

    # 竖分隔
    div_x = inner_x + block_w + vw(8)
    draw.line(
        [(div_x, cy_band - HEADER_DIVIDER_H // 2), (div_x, cy_band + HEADER_DIVIDER_H // 2)],
        fill=COLOR_HEAD_DIVIDER,
        width=HEADER_DIVIDER_W,
    )

    # 右：金 / 银 / 铜
    badge_x = div_x + vw(6)
    for badge, num in (
        (UMD_GOLD, progress.gold_umd_cnt),
        (UMD_SILVER, progress.silver_umd_cnt),
        (UMD_COPPER, progress.bronze_umd_cnt),
    ):
        w = _draw_umd_badge(
            canvas, draw, (badge_x, cy_band - UMD_BADGE_W * UMD_GOLD.height // UMD_GOLD.width // 2), badge, num
        )
        badge_x += w + UMD_GAP

    return bg_h


async def _draw_item(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    item: AchievementCategory,
) -> int:
    """gj：item_bg 全宽 + icon w-vw-64 + 类目名 + 右侧进度。"""
    x, y = xy
    bg = _scaled(ITEM_BG, width)
    canvas.alpha_composite(bg, (x, y))
    bg_h = bg.height
    cy = y + bg_h // 2

    icon = await _safe(get_achievement_img(item.id))
    icon_x = x + ITEM_ICON_LEFT
    if icon is not None:
        icon_img = icon.convert("RGBA").resize((ITEM_ICON_W, ITEM_ICON_W), Image.Resampling.LANCZOS)
        canvas.alpha_composite(icon_img, (icon_x, cy - ITEM_ICON_W // 2))

    name_x = icon_x + ITEM_ICON_W + ITEM_NAME_LEFT
    draw.text((name_x, cy), item.name, font=item_name_font, fill=COLOR_ITEM_TEXT, anchor="lm")

    progress_text = f"{item.progress}/{item.total}"
    draw.text((x + width - vw(20), cy), progress_text, font=item_prog_font, fill=COLOR_ITEM_TEXT, anchor="rm")

    return bg_h


async def draw_achievement_img(ev: Event, progress: AchievementProgress, role_name: str):
    user_avatar = await get_event_avatar(ev)
    avatar_block = make_head_avatar(user_avatar, size=AVATAR_SIZE, avatar_size=AVATAR_INNER)

    inner_w = WIDTH - PADDING * 2 - OUTER_PAD_X * 2
    items = progress.detail or []

    header_bg_h = round(HEADER_BG.height * inner_w / HEADER_BG.width)
    item_bg_h = round(ITEM_BG.height * inner_w / ITEM_BG.width)
    items_h = len(items) * item_bg_h + max(0, len(items) - 1) * ITEM_PAD_Y

    body_h = header_bg_h + (ITEM_GAP + items_h if items else 0)
    outer_h = body_h + OUTER_PAD_Y * 2

    body_top = AVATAR_Y + AVATAR_SIZE + BODY_TOP_GAP
    total_h = body_top + outer_h + FOOTER_RESERVE

    canvas = get_nte_bg(WIDTH, total_h).convert("RGBA")
    canvas.paste(get_nte_title_bg(WIDTH, HEADER_HEIGHT), (0, 0))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEADER_HEIGHT), COLOR_OVERLAY), (0, 0))

    draw = ImageDraw.Draw(canvas)
    title_right = WIDTH - PADDING
    draw.text((title_right, 34), "异环·成就进度", font=nte_font_42, fill=COLOR_WHITE, anchor="ra")
    draw.text((title_right, 96), role_name, font=nte_font_30, fill=COLOR_SUBTEXT, anchor="ra")
    canvas.alpha_composite(avatar_block, (AVATAR_X, AVATAR_Y))

    outer_x = PADDING
    outer_w = WIDTH - PADDING * 2
    outer_panel = Image.new("RGBA", (outer_w, outer_h), COLOR_OUTER)
    canvas.paste(outer_panel, (outer_x, body_top), rounded_mask((outer_w, outer_h), OUTER_RADIUS))

    inner_x = outer_x + OUTER_PAD_X
    cursor = body_top + OUTER_PAD_Y
    _draw_header(canvas, draw, (inner_x, cursor), inner_w, progress)
    cursor += header_bg_h + ITEM_GAP

    for idx, item in enumerate(items):
        await _draw_item(canvas, draw, (inner_x, cursor), inner_w, item)
        cursor += item_bg_h
        if idx < len(items) - 1:
            cursor += ITEM_PAD_Y

    add_footer(canvas)
    return await convert_img(canvas)
