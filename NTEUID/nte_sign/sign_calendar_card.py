from __future__ import annotations

from typing import List
from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    vw,
    add_footer,
    cache_name,
    get_nte_bg,
    open_texture,
    rounded_mask,
    make_nte_role_title,
    download_pic_from_url,
)
from ..utils.game_registry import GAME_LABELS
from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.sdk.tajiduo_model import GameSignState, GameSignReward
from ..utils.resource.RESOURCE_PATH import SIGN_CALENDAR_PATH

WIDTH = 1180
FOOTER_RESERVE = 80

# 网格容器（对应官方 `flex grid grid-cols-4 px-12p py-10p gap-x-14p gap-y-12p`）
PANEL_RADIUS = vw(12)
PANEL_PAD_X = vw(12)
GRID_COLS = 4
GRID_GAP_X = vw(14)
GRID_GAP_Y = vw(12)

# 单元格：官方 `w-78.5p h-96p`
CELL_W = vw(78.5)
CELL_H = vw(96)
CELL_DAY_FONT = vw(12)
CELL_NUM_FONT = vw(10)
CELL_NUM_RIGHT_PAD = vw(4)
CELL_BOTTOM_PAD = vw(4)
CELL_TEXT_GAP = vw(2)
CELL_ICON_SIZE = vw(56)
CELL_ICON_TOP = vw(8)

# sign_header.png 内分层（源 960×1350）；粉线占 168~177 共 9 行
SIGN_HEADER_DARK_END = 168
SIGN_HEADER_PINK_END = 177

# sign_logo.png：NTE title 与面板之间居中
SIGN_LOGO_W = vw(220)
SIGN_LOGO_BOTTOM_GAP = vw(10)

SUMMARY_HEIGHT = vw(64)
SUMMARY_LABEL_FONT = vw(11)
SUMMARY_VALUE_FONT = vw(20)
SUMMARY_VALUE_TOP = vw(11)
SUMMARY_VALUE_LABEL_GAP = vw(4)
SUMMARY_DIVIDER_INSET = vw(14)

GRID_TOP_GAP = vw(10)
DISCLAIMER_FONT = vw(10)
DISCLAIMER_TOP = vw(16)
DISCLAIMER_BOTTOM = vw(14)
PANEL_BOTTOM_PAD = vw(16)

COLOR_SUMMARY_LABEL = (170, 170, 175)
COLOR_DIVIDER = (75, 75, 80)
COLOR_NUM_DARK = (51, 51, 51)
COLOR_DISCLAIMER = (112, 112, 112)

TEXTURE_PATH = Path(__file__).parent / "texture2d" / "sign"


CELL_ENABLE = open_texture(TEXTURE_PATH / "cell_enable.png", (CELL_W, CELL_H))
CELL_DISABLE = open_texture(TEXTURE_PATH / "cell_disable.png", (CELL_W, CELL_H))
CELL_DONE = open_texture(TEXTURE_PATH / "cell_done.png", (CELL_W, CELL_H))

_SIGN_HEADER_RAW = open_texture(TEXTURE_PATH / "sign_header.png")


def _scaled(name: str, target_w: int) -> Image.Image:
    raw = open_texture(TEXTURE_PATH / name)
    new_h = round(raw.height * target_w / raw.width)
    return raw.resize((target_w, new_h), Image.Resampling.LANCZOS)


def _sign_header_slice(width: int, top: int, bottom: int) -> Image.Image:
    crop = _SIGN_HEADER_RAW.crop((0, top, _SIGN_HEADER_RAW.width, bottom))
    new_h = round(crop.height * width / crop.width)
    return crop.resize((width, new_h), Image.Resampling.LANCZOS)


def _sign_header_body(width: int, height: int) -> Image.Image:
    crop = _SIGN_HEADER_RAW.crop((0, SIGN_HEADER_PINK_END, _SIGN_HEADER_RAW.width, _SIGN_HEADER_RAW.height))
    return crop.resize((width, height), Image.Resampling.LANCZOS)


SIGN_LOGO = _scaled("sign_logo.png", SIGN_LOGO_W)
summary_label_font = nte_font_origin(SUMMARY_LABEL_FONT)
summary_value_font = nte_font_origin(SUMMARY_VALUE_FONT)
day_font = nte_font_origin(CELL_DAY_FONT)
num_font = nte_font_origin(CELL_NUM_FONT)
disclaimer_font = nte_font_origin(DISCLAIMER_FONT)


async def _load_reward_icon(url: str) -> Image.Image | None:
    """缓存签到奖励图标；下载失败返回 None，由调用方占位。"""
    if not url:
        return None
    try:
        img = await download_pic_from_url(SIGN_CALENDAR_PATH, url, name=cache_name("reward", url))
    except OSError:
        return None
    return img.convert("RGBA").resize((CELL_ICON_SIZE, CELL_ICON_SIZE), Image.Resampling.LANCZOS)


def _classify(day_index: int, state: GameSignState) -> str:
    """对齐官方 yh-signin webview：`signed = n < days`，`canSign = n == days && !todaySign`，其余 future。
    `state.days` 是本月累计签到次数（不是月长），`state.day` 这里不参与逐格判定。"""
    if day_index < state.days:
        return "signed"
    if day_index == state.days:
        return "signed" if state.today_sign else "today"
    return "future"


def _draw_cell(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    day_index: int,
    reward: GameSignReward,
    icon: Image.Image | None,
    kind: str,
) -> None:
    x, y = xy
    bg = CELL_ENABLE if kind == "today" else CELL_DISABLE
    canvas.alpha_composite(bg, (x, y))

    if icon is not None:
        canvas.alpha_composite(icon, (x + (CELL_W - CELL_ICON_SIZE) // 2, y + CELL_ICON_TOP))

    cx = x + CELL_W // 2
    day_y = y + CELL_H - CELL_BOTTOM_PAD - int(day_font.size)
    draw.text((cx, day_y), f"第{day_index + 1}天", font=day_font, fill=COLOR_WHITE, anchor="mt")

    num_y = day_y - CELL_TEXT_GAP - int(num_font.size)
    draw.text(
        (x + CELL_W - CELL_NUM_RIGHT_PAD, num_y),
        f"x{reward.num}",
        font=num_font,
        fill=COLOR_NUM_DARK,
        anchor="rt",
    )

    if kind == "signed":
        canvas.alpha_composite(CELL_DONE, (x, y))


def _draw_summary_row(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    width: int,
    state: GameSignState,
) -> None:
    """4 列统计：本月 / 累计签到 / 今日 / 可补签。直接画在烘焙暗带上，不重画底。"""
    x, y = xy
    items = [
        (f"{state.month}月", "本月"),
        (f"{state.days}天", "累计签到"),
        ("已签" if state.today_sign else "未签", "今日"),
        (str(state.re_sign_cnt), "可补签"),
    ]
    cell_w = width // len(items)
    cy_value = y + SUMMARY_VALUE_TOP
    cy_label = cy_value + int(summary_value_font.size) + SUMMARY_VALUE_LABEL_GAP
    for idx, (value, label) in enumerate(items):
        cx = x + cell_w * idx + cell_w // 2
        draw.text((cx, cy_value), value, font=summary_value_font, fill=COLOR_WHITE, anchor="mt")
        draw.text((cx, cy_label), label, font=summary_label_font, fill=COLOR_SUMMARY_LABEL, anchor="mt")
        if idx < len(items) - 1:
            sep_x = x + cell_w * (idx + 1)
            draw.line(
                [(sep_x, y + SUMMARY_DIVIDER_INSET), (sep_x, y + SUMMARY_HEIGHT - SUMMARY_DIVIDER_INSET)],
                fill=COLOR_DIVIDER,
                width=1,
            )


PANEL_W = GRID_COLS * CELL_W + (GRID_COLS - 1) * GRID_GAP_X + PANEL_PAD_X * 2
PANEL_X = (WIDTH - PANEL_W) // 2


async def draw_sign_calendar_img(
    ev: Event,
    state: GameSignState,
    rewards: List[GameSignReward],
    role_name: str,
    uid: str,
    game_id: str,
):
    rewards = list(rewards)
    rows = (len(rewards) + GRID_COLS - 1) // GRID_COLS
    grid_h = rows * CELL_H + max(0, rows - 1) * GRID_GAP_Y

    user_avatar = await get_event_avatar(ev)
    title = make_nte_role_title(user_avatar, role_name, uid)

    baked_dark = _sign_header_slice(PANEL_W, 0, SIGN_HEADER_DARK_END)
    pink_strip = _sign_header_slice(PANEL_W, SIGN_HEADER_DARK_END, SIGN_HEADER_PINK_END)
    baked_h = baked_dark.height
    dark_total_h = baked_h + pink_strip.height

    body_inner_h = (
        GRID_TOP_GAP + grid_h + DISCLAIMER_TOP + int(disclaimer_font.size) + DISCLAIMER_BOTTOM + PANEL_BOTTOM_PAD
    )
    panel_h = dark_total_h + body_inner_h

    body_top = 30 + title.height
    panel_top = body_top + SIGN_LOGO.height + SIGN_LOGO_BOTTOM_GAP
    total_height = panel_top + panel_h + FOOTER_RESERVE

    game_label = GAME_LABELS[game_id]
    canvas = get_nte_bg(WIDTH, total_height).convert("RGBA")
    canvas.alpha_composite(title, (40, 30))

    draw = ImageDraw.Draw(canvas)
    canvas.alpha_composite(SIGN_LOGO, ((WIDTH - SIGN_LOGO.width) // 2, body_top))

    panel_layer = Image.new("RGBA", (PANEL_W, panel_h), (0, 0, 0, 0))
    panel_layer.alpha_composite(baked_dark, (0, 0))
    panel_layer.alpha_composite(pink_strip, (0, baked_h))
    panel_layer.alpha_composite(_sign_header_body(PANEL_W, body_inner_h), (0, dark_total_h))
    canvas.paste(panel_layer, (PANEL_X, panel_top), rounded_mask((PANEL_W, panel_h), PANEL_RADIUS))

    inner_x = PANEL_X + PANEL_PAD_X
    summary_y = panel_top + (baked_h - SUMMARY_HEIGHT) // 2
    _draw_summary_row(draw, (inner_x, summary_y), PANEL_W - PANEL_PAD_X * 2, state)

    grid_y = panel_top + dark_total_h + GRID_TOP_GAP
    icons = [await _load_reward_icon(reward.icon) for reward in rewards]
    for index, (reward, icon) in enumerate(zip(rewards, icons)):
        x = inner_x + (index % GRID_COLS) * (CELL_W + GRID_GAP_X)
        y = grid_y + (index // GRID_COLS) * (CELL_H + GRID_GAP_Y)
        _draw_cell(canvas, draw, (x, y), index, reward, icon, _classify(index, state))

    draw.text(
        (PANEL_X + PANEL_W // 2, grid_y + grid_h + DISCLAIMER_TOP),
        f"（签到奖励可能存在延迟，请前往《{game_label}》游戏内邮箱领取）",
        font=disclaimer_font,
        fill=COLOR_DISCLAIMER,
        anchor="mt",
    )

    add_footer(canvas)
    return await convert_img(canvas)
