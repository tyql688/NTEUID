from __future__ import annotations

from pathlib import Path
from functools import lru_cache
from dataclasses import dataclass

from PIL import Image, ImageDraw, ImageChops

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img

from ..utils.image import COLOR_WHITE, SmoothDrawer, add_footer, get_nte_bg, open_texture, char_img_ring
from ..utils.avatar import fetch_avatar
from ..utils.resource.cdn import get_char_detail_img, get_char_suit_detail_img
from ..utils.fonts.nte_fonts import nte_font_origin

CHAR_TEX = Path(__file__).parent / "texture2d" / "character"
RANK_TEX = Path(__file__).parent / "texture2d" / "rank"

WIDTH = 1280
HEADER_H = 430
ROW_H = 152
ROW_GAP = 16
PANEL_X0 = 30
PANEL_W = 1250 - PANEL_X0
AVATAR = 124

# 配色取自官方异环主视觉：深靛蓝底 + 暖奶油高光。
INDIGO_TOP = (54, 50, 86)
INDIGO_BOTTOM = (28, 26, 48)
CREAM = (251, 221, 188)
SUBTEXT = (192, 190, 224)
SELF_NAME = (255, 96, 96)
GRADE_COLOR = {"S": (255, 208, 96), "A": (170, 165, 240), "B": (176, 182, 214)}
TIER_FRAME = {1: "frame_1.png", 2: "frame_2.png", 3: "frame_3.png"}


@dataclass(frozen=True, slots=True)
class RankEntry:
    user_id: str
    role_name: str
    uid: str
    awaken_lev: int
    suit_id: str
    suit_name: str
    suit_pieces: int
    score: int
    grade: str


@lru_cache(maxsize=8)
def _asset(name: str) -> Image.Image:
    return open_texture(RANK_TEX / name)


@lru_cache(maxsize=4)
def _tier_frame(rank: int) -> Image.Image:
    """名次行卡边框图（1/2/3 红金银，其余 frame_n）；裁掉透明留白后铺满整行宽高。"""
    img = _asset(TIER_FRAME.get(rank, "frame_n.png"))
    return img.crop(img.split()[3].getbbox()).resize((PANEL_W, ROW_H), Image.Resampling.LANCZOS)


def _fit(draw: ImageDraw.ImageDraw, text: str, width: int, font) -> str:
    if round(draw.textlength(text, font=font)) <= width:
        return text
    while text and round(draw.textlength(f"{text}...", font=font)) > width:
        text = text[:-1]
    return f"{text}..." if text else "..."


def _vgradient(h: int, top: tuple[int, int, int], bottom: tuple[int, int, int], alpha: int) -> Image.Image:
    """竖直渐变层（top→bottom，固定 alpha），统一整图色温。"""
    strip = Image.new("RGBA", (1, h))
    for y in range(h):
        t = y / max(1, h - 1)
        strip.putpixel((0, y), tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3)) + (alpha,))
    return strip.resize((WIDTH, h), Image.Resampling.BILINEAR)


def _fade_left(img: Image.Image, frac: float = 0.45) -> Image.Image:
    """立绘左→右渐显，叠在原 alpha 上，融进 banner。"""
    out = img.convert("RGBA")
    w, h = out.size
    grad = Image.new("L", (w, 1))
    edge = max(1, int(w * frac))
    for x in range(w):
        grad.putpixel((x, 0), min(255, round(255 * x / edge)))
    out.putalpha(ImageChops.multiply(out.split()[3], grad.resize((w, h))))
    return out


async def _draw_row(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    y: int,
    rank: int,
    entry: RankEntry,
    avatar: Image.Image,
    is_self: bool,
) -> None:
    canvas.alpha_composite(_tier_frame(rank), (PANEL_X0, y))
    mid = y + ROW_H // 2
    # 名次圈：复用头像同款圆环 head_ring，里面填深底再写名次
    canvas.alpha_composite(char_img_ring(Image.new("RGBA", (96, 96), (26, 22, 44, 255)), 96), (60, mid - 48))
    rank_text = "最强" if rank == 1 else str(rank)
    draw.text(
        (108, mid + 1),
        rank_text,
        font=nte_font_origin(26 if rank == 1 else 48),
        fill=CREAM if rank == 1 else COLOR_WHITE,
        anchor="mm",
    )
    # 头像 + 觉醒角标
    ay = y + (ROW_H - AVATAR) // 2
    canvas.alpha_composite(char_img_ring(avatar, AVATAR), (172, ay))
    SmoothDrawer().rounded_rectangle((226, ay + 80, 292, ay + 116), 18, fill=(140, 120, 228, 245), target=canvas)
    draw.text((259, ay + 98), f"{entry.awaken_lev}觉", font=nte_font_origin(24), fill=COLOR_WHITE, anchor="mm")
    # 名字（自己标红；无身份的孤儿行留空）+ UID
    name = _fit(draw, entry.role_name, 200, nte_font_origin(38))
    draw.text((320, mid - 24), name, font=nte_font_origin(38), fill=SELF_NAME if is_self else COLOR_WHITE, anchor="lm")
    draw.text((320, mid + 28), f"UID {entry.uid}", font=nte_font_origin(22), fill=SUBTEXT, anchor="lm")
    # 套装图标 + 名称·件数
    icon = await get_char_suit_detail_img(entry.suit_id) if entry.suit_id else None
    if icon is not None:
        canvas.alpha_composite(icon.convert("RGBA").resize((78, 78), Image.Resampling.LANCZOS), (540, mid - 39))
    text = _fit(draw, f"{entry.suit_name} · {entry.suit_pieces}件", 380, nte_font_origin(28))
    draw.text((632, mid), text, font=nte_font_origin(28), fill=COLOR_WHITE, anchor="lm")
    # 评级图标 + 分数（按评级配色）
    grade = entry.grade
    if grade in GRADE_COLOR:
        canvas.alpha_composite(open_texture(CHAR_TEX / f"rank_{grade}.png", (76, 76)), (1014, mid - 38))
    draw.text(
        (1196, mid - 16),
        str(entry.score),
        font=nte_font_origin(52),
        fill=GRADE_COLOR.get(grade, COLOR_WHITE),
        anchor="rm",
    )
    draw.text((1196, mid + 33), "分", font=nte_font_origin(22), fill=SUBTEXT, anchor="rm")


async def _draw_header(
    canvas: Image.Image, draw: ImageDraw.ImageDraw, char_name: str, char_id: str, total: int, scope_label: str
) -> None:
    # 标题压暗罩：顶部留出霓虹天际线，越往下越暗
    scrim = Image.new("RGBA", (1, HEADER_H))
    for y in range(HEADER_H):
        scrim.putpixel((0, y), (14, 12, 28, int(24 + 182 * (y / (HEADER_H - 1)) ** 1.7)))
    canvas.alpha_composite(scrim.resize((WIDTH, HEADER_H), Image.Resampling.BILINEAR), (0, 0))
    # 右侧 fashion 立绘：取上半身（顶部 60%）放大铺满标题区
    art = await get_char_detail_img(char_id)
    if art is not None:
        upper = art.convert("RGBA").crop((0, 0, art.width, int(art.height * 0.6)))
        w = round(upper.width * (HEADER_H + 24) / upper.height)
        canvas.alpha_composite(
            _fade_left(upper.resize((w, HEADER_H + 24), Image.Resampling.LANCZOS)), (WIDTH - w + 60, -12)
        )
    logo = _asset("logo_yh.png")
    canvas.alpha_composite(
        logo.resize((round(logo.width * 168 / logo.height), 168), Image.Resampling.LANCZOS), (48, 50)
    )
    draw.text((52, 304), f"「{char_name}」评分排名", font=nte_font_origin(64), fill=COLOR_WHITE, anchor="lm")
    SmoothDrawer().rounded_rectangle((54, 346, 318, 353), 3, fill=(251, 221, 188, 240), target=canvas)
    draw.text(
        (56, 380), f"{scope_label} {total} 个号上榜 · 按评分降序", font=nte_font_origin(28), fill=SUBTEXT, anchor="lm"
    )


async def draw_rank_img(
    ev: Event,
    char_name: str,
    char_id: str,
    entries: list[RankEntry],
    total: int,
    scope_label: str,
    self_overflow: tuple[int, RankEntry] | None = None,
) -> bytes:
    # 展示行 = 前 N 名 (+ 自己掉榜时榜尾补一行真实名次)
    display = [(i + 1, e, e.user_id == ev.user_id) for i, e in enumerate(entries)]
    if self_overflow is not None:
        display.append((self_overflow[0], self_overflow[1], True))
    avatars = [await fetch_avatar(ev, e.user_id, char_id) for _, e, _ in display]

    overflow_gap = 34 if self_overflow is not None else 0
    height = HEADER_H + len(display) * ROW_H + max(0, len(display) - 1) * ROW_GAP + overflow_gap + 110

    canvas = get_nte_bg(WIDTH, height, bg="bg4").convert("RGBA")
    canvas.alpha_composite(_vgradient(height, INDIGO_TOP, INDIGO_BOTTOM, 70))
    draw = ImageDraw.Draw(canvas)
    await _draw_header(canvas, draw, char_name, char_id, total, scope_label)

    y = HEADER_H
    for index, ((rank, entry, is_self), avatar) in enumerate(zip(display, avatars)):
        if self_overflow is not None and index == len(display) - 1:
            draw.text((WIDTH // 2, y + 15), "· · ·", font=nte_font_origin(30), fill=SUBTEXT, anchor="mm")
            y += overflow_gap
        await _draw_row(canvas, draw, y, rank, entry, avatar, is_self)
        y += ROW_H + ROW_GAP

    add_footer(canvas)
    return await convert_img(canvas)
