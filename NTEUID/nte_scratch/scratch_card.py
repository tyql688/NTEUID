from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.image import (
    COLOR_DARK,
    COLOR_GREEN,
    COLOR_MUTED,
    COLOR_ORANGE,
    COLOR_RED,
    COLOR_WHITE,
    DEFAULT_CARD_RADIUS,
    SmoothDrawer,
    add_footer,
    get_nte_bg,
    make_nte_role_title,
    open_texture,
    vw,
)

WIDTH = 1180
PAD_X = 40
PANEL_W = WIDTH - PAD_X * 2
RADIUS = DEFAULT_CARD_RADIUS
TEX = Path(__file__).resolve().parent.parent / "nte_role" / "texture2d" / "character"

# 角色面板风格配色（深紫黑 + 洋红描边 + 橙金强调）
BG_PANEL = (22, 24, 38, 240)      # 深紫黑面板底
BG_CELL = (30, 33, 50, 235)       # 单元格底
BG_ROW_ALT = (46, 40, 60, 150)    # 明细交替行（偏紫）
SEP_COLOR = (72, 66, 90)
MAGENTA = (255, 78, 128)          # 洋红点缀 #FF4E80
GOLD = COLOR_ORANGE
GOLD_HI = (255, 161, 37)          # 橙金强调 #FFA125
GOLD_SOFT = (255, 196, 92)
LIGHT_MUTED = (190, 184, 206)     # 浅紫灰，提升深色底可读性
BORDER_MAGENTA = (255, 78, 128, 80)  # 卡片细洋红描边

TITLE_TOP = 24
BANNER_TOP = TITLE_TOP + 216 + 16
BANNER_H = 56
MAIN_TOP = BANNER_TOP + BANNER_H + 18
MAIN_H = vw(196)
GRID_TOP = MAIN_TOP + MAIN_H + 20
GRID_COLS = 4
GRID_GAP = vw(14)
CELL_W = (PANEL_W - (GRID_COLS - 1) * GRID_GAP) // GRID_COLS
CELL_H = vw(76)
CELL_GAP_Y = vw(12)
WIDE_Y = GRID_TOP + 4 * (CELL_H + CELL_GAP_Y)
DETAIL_TOP = WIDE_Y + CELL_H + 20
DETAIL_HEADER_H = 46
DETAIL_ROW_H = 46
FOOTER_RESERVE = 132


def _fmt(value: int) -> str:
    return f"{value:,}"


def _fmt_wan(value: int) -> str:
    """金额缩写：≥1万 用「万」单位（如 380000 → 38万，12000 → 1.2万）。"""
    num = abs(int(value))
    sign = "-" if value < 0 else ""
    if num >= 10000:
        wan = num / 10000
        text = f"{wan:.1f}" if wan % 1 else f"{wan:.0f}"
        return f"{sign}{text}万"
    return f"{sign}{num:,}"


def _fmt_rate(value: float) -> str:
    return f"{value:+.2f}%" if value < 0 else f"{value:.2f}%"


def _fit_font(
    draw: ImageDraw.ImageDraw,
    text: str,
    size: int,
    max_width: int,
) -> Any:
    """字号超宽时逐级缩小，保证文字不溢出容器。"""
    font = nte_font_origin(size)
    while font.size > 18 and draw.textlength(text, font=font) > max_width:
        size -= 2
        font = nte_font_origin(size)
    return font


def aggregate_books(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """读物汇总：同一种读物按次数聚合，返回 [{name, count, gain}]（按总奖励倒序）。"""
    import re

    def book_name(record: dict[str, Any]) -> str:
        for key in ("scratchCardId", "activityName", "activity", "name", "itemName", "description", "title", "content"):
            value = record.get(key)
            if value:
                return str(value)
        return "未知读物"

    def book_award(record: dict[str, Any]) -> int:
        award_text = ""
        for key in ("award", "awardText", "totalReward", "amount", "itemAmount", "gain", "reward"):
            value = record.get(key)
            if value not in (None, ""):
                award_text = str(value)
                break
        match = re.search(r"方斯\s*[*×xX]\s*([0-9][0-9,]*)", award_text)
        if match:
            return int(match.group(1).replace(",", ""))
        match = re.search(r"([0-9][0-9,]*)", award_text)
        return int(match.group(1).replace(",", "")) if match else 0

    grouped: dict[str, dict[str, Any]] = {}
    for record in records:
        name = book_name(record)
        item = grouped.setdefault(name, {"name": name, "count": 0, "gain": 0})
        item["count"] += 1
        item["gain"] += book_award(record)
    return sorted(grouped.values(), key=lambda r: (r["gain"], r["count"]), reverse=True)[:12]


def _rounded_layer(w: int, h: int, color: tuple, radius: int) -> Image.Image:
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(layer).rounded_rectangle((0, 0, w, h), radius=radius, fill=color)
    return layer


def _panel(
    canvas: Image.Image,
    x: int,
    y: int,
    w: int,
    h: int,
    radius: int,
    fill: tuple,
    *,
    outline: tuple | None = None,
) -> None:
    """角色面板风格圆角面板：抗锯齿 + 可选细描边。"""
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    SmoothDrawer().rounded_rectangle(
        (0, 0, w, h),
        radius,
        fill=fill,
        outline=outline,
        width=2 if outline else 0,
        target=layer,
    )
    canvas.alpha_composite(layer, (x, y))


def _drive_bg(size: tuple[int, int]) -> Image.Image:
    """角色面板驱动块卡片背景：等比缩放 + 居中裁切，保留票券穿孔边缘。"""
    img = open_texture(TEX / "ad_bg.png")
    w, h = size
    scale = w / img.width
    resized = img.resize((w, max(h, round(img.height * scale))), Image.Resampling.LANCZOS)
    top = (resized.height - h) // 2
    return resized.crop((0, top, w, top + h))


def _draw_banner(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    start: date,
    end: date,
    days: int,
) -> None:
    """金色标题条：左标题 + 右查询范围。"""
    _panel(canvas, x, y, w, BANNER_H, RADIUS, BG_PANEL, outline=BORDER_MAGENTA)
    # 左侧洋红竖条
    draw.rounded_rectangle(
        (x + 20, y + 14, x + 26, y + BANNER_H - 14),
        radius=3,
        fill=MAGENTA,
    )
    draw.text(
        (x + 42, y + BANNER_H // 2),
        "刮刮乐战报",
        font=nte_font_origin(vw(18)),
        fill=GOLD_HI,
        anchor="lm",
    )
    draw.text(
        (x + w - 22, y + BANNER_H // 2),
        f"{start:%m-%d} ~ {end:%m-%d} · 近 {days} 天",
        font=nte_font_origin(vw(12)),
        fill=LIGHT_MUTED,
        anchor="rm",
    )


def _draw_main_panel(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    stats: dict[str, Any],
) -> None:
    _panel(canvas, x, y, w, MAIN_H, RADIUS, BG_PANEL, outline=BORDER_MAGENTA)
    # 顶部洋红高光线
    draw.rounded_rectangle(
        (x + 24, y + 18, x + w - 24, y + 20),
        radius=1,
        fill=MAGENTA,
    )

    net = stats["net"]
    net_color = COLOR_GREEN if net >= 0 else COLOR_RED
    recovery = stats["recovery"]
    recovery_color = COLOR_GREEN if recovery >= 100 else COLOR_RED
    label_font = nte_font_origin(vw(14))

    # 左：净盈亏
    left_w = int(w * 0.42)
    lcx = x + left_w // 2
    draw.text((lcx, y + vw(38)), "净盈亏（方斯）", font=label_font, fill=LIGHT_MUTED, anchor="mm")
    net_text = f"{'+' if net >= 0 else ''}{_fmt(net)}"
    net_font = _fit_font(draw, net_text, vw(40), left_w - vw(32))
    draw.text((lcx, y + vw(112)), net_text, font=net_font, fill=net_color, anchor="mm")

    # 中：回本率（带进度条）
    mid_w = int(w * 0.30)
    mcx = x + left_w + mid_w // 2
    draw.text((mcx, y + vw(38)), "回本率", font=label_font, fill=LIGHT_MUTED, anchor="mm")
    draw.text(
        (mcx, y + vw(92)),
        _fmt_rate(recovery),
        font=nte_font_origin(vw(26)),
        fill=recovery_color,
        anchor="mm",
    )
    bar_x = x + left_w + vw(22)
    bar_y = y + vw(118)
    bar_w = mid_w - vw(44)
    bar_h = vw(10)
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + bar_w, bar_y + bar_h),
        radius=bar_h // 2,
        fill=(55, 65, 82),
    )
    fill_w = max(vw(10), int(bar_w * min(recovery, 140) / 100))
    draw.rounded_rectangle(
        (bar_x, bar_y, bar_x + fill_w, bar_y + bar_h),
        radius=bar_h // 2,
        fill=recovery_color,
    )
    draw.text(
        (mcx, y + vw(158)),
        "（≥100% 即回本）",
        font=nte_font_origin(vw(13)),
        fill=LIGHT_MUTED,
        anchor="mm",
    )

    # 右：返还金额
    right_w = w - left_w - mid_w
    rcx = x + left_w + mid_w + right_w // 2
    draw.text((rcx, y + vw(38)), "返还金额", font=label_font, fill=LIGHT_MUTED, anchor="mm")
    gain_text = _fmt(stats["total_gain"])
    gain_font = _fit_font(draw, gain_text, vw(26), right_w - vw(44))
    draw.text((rcx, y + vw(112)), gain_text, font=gain_font, fill=COLOR_WHITE, anchor="mm")

    # 竖向分隔线
    for sx in (x + left_w, x + left_w + mid_w):
        draw.line(
            [(sx, y + vw(28)), (sx, y + MAIN_H - vw(28))],
            fill=SEP_COLOR,
            width=1,
        )


def _draw_stat_grid(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    stats: dict[str, Any],
) -> None:
    items = [
        ("投入", _fmt(stats["total_cost"])),
        ("返还", _fmt(stats["total_gain"])),
        ("奖励流水", _fmt(stats["flow"])),
        ("命中率", f"{stats['hit_rate']:.2f}%"),
        ("有奖次数", str(stats["win_count"])),
        ("空奖次数", str(stats["empty_count"])),
        ("平均奖励", _fmt(round(stats["avg_award"]))),
        ("最高单项", _fmt(stats["max_award"])),
        ("大奖次数", str(stats["big_count"])),
        ("最高奖占比", f"{stats['big_ratio']:.2f}%"),
        ("卡面种类", str(stats["card_kinds"])),
        ("活跃天数", str(stats["active_days"])),
        ("盈亏幅度", _fmt_rate(stats["profit_rate"])),
        ("最大连空", str(stats["max_consecutive_losses"])),
        ("总记录", str(stats["total"])),
        ("官网分页", str(stats["pages"])),
    ]
    label_font = nte_font_origin(vw(14))
    for index, (label, value) in enumerate(items):
        row, col = divmod(index, GRID_COLS)
        cell_x = x + col * (CELL_W + GRID_GAP)
        cell_y = y + row * (CELL_H + CELL_GAP_Y)
        canvas.alpha_composite(_drive_bg((CELL_W, CELL_H)), (cell_x, cell_y))
        _panel(canvas, cell_x, cell_y, CELL_W, CELL_H, vw(10), (8, 10, 18, 120), outline=BORDER_MAGENTA)
        cx = cell_x + CELL_W // 2
        value_color = COLOR_WHITE
        if label in ("盈亏幅度", "最大连空"):
            value_color = COLOR_RED if (label == "盈亏幅度" and stats["profit_rate"] < 0) else COLOR_GREEN
        if label == "命中率":
            value_color = GOLD_HI
        value_font = _fit_font(draw, value, vw(18), CELL_W - vw(16))
        label_fitted = _fit_font(draw, label, vw(14), CELL_W - vw(16))
        draw.text((cx, cell_y + vw(22)), label, font=label_fitted, fill=LIGHT_MUTED, anchor="mm")
        draw.text((cx, cell_y + vw(50)), value, font=value_font, fill=value_color, anchor="mm")

    best_day, best_net = stats["best_day"]
    worst_day, worst_net = stats["worst_day"]
    _panel(canvas, x, WIDE_Y, w, CELL_H, vw(10), BG_CELL, outline=BORDER_MAGENTA)
    half = w // 2
    for cx, label, day, value in (
        (x + half // 2, "最佳单日", best_day, best_net),
        (x + half + half // 2, "最差单日", worst_day, worst_net),
    ):
        color = COLOR_GREEN if value >= 0 else COLOR_RED
        draw.text((cx, WIDE_Y + vw(22)), label, font=label_font, fill=LIGHT_MUTED, anchor="mm")
        value_text = f"{day[5:]} {'+' if value >= 0 else ''}{_fmt(value)}" if day else "--"
        value_fitted = _fit_font(draw, value_text, vw(18), half - vw(24))
        draw.text((cx, WIDE_Y + vw(50)), value_text, font=value_fitted, fill=color, anchor="mm")
    draw.line(
        [(x + half, WIDE_Y + vw(14)), (x + half, WIDE_Y + CELL_H - vw(14))],
        fill=SEP_COLOR,
        width=1,
    )


def _draw_detail(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    w: int,
    records: list[dict[str, Any]],
) -> None:
    """读物汇总：同一种读物按次数聚合（《荧幕之外》×60），不再逐条列出。"""
    rows = aggregate_books(records)

    draw.text(
        (x, y),
        "读物汇总",
        font=nte_font_origin(vw(20)),
        fill=COLOR_WHITE,
        anchor="lt",
    )
    table_top = y + 72
    table_h = DETAIL_HEADER_H + len(rows) * DETAIL_ROW_H + 23
    _panel(canvas, x, table_top, w, table_h, vw(10), BG_PANEL, outline=BORDER_MAGENTA)

    col_x = [x, x + 40, x + 560]
    header_font = nte_font_origin(vw(15))
    row_font = nte_font_origin(vw(15))
    draw.text((col_x[1] + 18, table_top + DETAIL_HEADER_H // 2), "读物", font=header_font, fill=LIGHT_MUTED, anchor="lm")
    draw.text((col_x[2] + 18, table_top + DETAIL_HEADER_H // 2), "次数", font=header_font, fill=LIGHT_MUTED, anchor="lm")
    draw.text((x + w - 24, table_top + DETAIL_HEADER_H // 2), "总奖励（方斯）", font=header_font, fill=LIGHT_MUTED, anchor="rm")
    draw.line(
        [(x + vw(14), table_top + DETAIL_HEADER_H), (x + w - vw(14), table_top + DETAIL_HEADER_H)],
        fill=SEP_COLOR,
        width=1,
    )

    for index, item in enumerate(rows):
        row_y = table_top + DETAIL_HEADER_H + index * DETAIL_ROW_H + DETAIL_ROW_H // 2
        if index % 2 == 1:
            draw.rectangle(
                (
                    x + vw(18),
                    table_top + DETAIL_HEADER_H + index * DETAIL_ROW_H,
                    x + w - vw(18),
                    table_top + DETAIL_HEADER_H + (index + 1) * DETAIL_ROW_H,
                ),
                fill=BG_ROW_ALT,
            )
        name_text = item["name"]
        name_font = _fit_font(draw, name_text, vw(15), col_x[2] - col_x[1] - 40)
        count_text = f"×{item['count']}"
        gain_text = _fmt(item["gain"])
        gain_font = _fit_font(draw, gain_text, vw(15), x + w - col_x[2] - 60)
        draw.text((col_x[1] + 18, row_y), name_text, font=name_font, fill=COLOR_WHITE, anchor="lm")
        draw.text((col_x[2] + 18, row_y), count_text, font=row_font, fill=LIGHT_MUTED, anchor="lm")
        draw.text((x + w - 24, row_y), gain_text, font=gain_font, fill=GOLD_HI, anchor="rm")


async def draw_scratch_card_img(
    ev: Event,
    role_name: str,
    uid: str,
    start: date,
    end: date,
    days: int,
    stats: dict[str, Any],
    records: list[dict[str, Any]],
):
    book_rows = aggregate_books(records)
    detail_h = 72 + DETAIL_HEADER_H + len(book_rows) * DETAIL_ROW_H + 23
    total_height = DETAIL_TOP + detail_h + 26 + FOOTER_RESERVE

    user_avatar = await get_event_avatar(ev)
    title = make_nte_role_title(user_avatar, role_name, uid)
    canvas = get_nte_bg(WIDTH, total_height, bg="bg3").convert("RGBA")
    canvas.alpha_composite(title, (PAD_X, TITLE_TOP))
    draw = ImageDraw.Draw(canvas)

    _draw_banner(canvas, draw, PAD_X, BANNER_TOP, PANEL_W, start, end, days)
    _draw_main_panel(canvas, draw, PAD_X, MAIN_TOP, PANEL_W, stats)
    _draw_stat_grid(canvas, draw, PAD_X, GRID_TOP, PANEL_W, stats)
    _draw_detail(canvas, draw, PAD_X, DETAIL_TOP, PANEL_W, records)

    draw.text(
        (WIDTH // 2, DETAIL_TOP + detail_h + 34),
        "数据来源：完美世界官方客服系统（kf.wanmei.com）",
        font=nte_font_origin(vw(14)),
        fill=COLOR_MUTED,
        anchor="mt",
    )
    add_footer(canvas)
    return await convert_img(canvas)


async def draw_scratch_rank_img(
    ev: Event,
    entries: list[dict[str, Any]],
) -> bytes:
    """群内刮刮乐亏损排行卡：亏损越多排名越高。"""
    RANK_W = 1180
    RANK_PAD = 40
    panel_w = RANK_W - RANK_PAD * 2
    top_h = 130
    head_h = 52
    row_h = 66
    table_bottom_pad = 22
    total_height = (
        20
        + top_h
        + 14
        + head_h
        + len(entries) * row_h
        + table_bottom_pad
        + 24
        + 40
        + 120
    )

    canvas = get_nte_bg(RANK_W, total_height, bg="bg3").convert("RGBA")
    draw = ImageDraw.Draw(canvas)
    _panel(canvas, RANK_PAD, 20, panel_w, top_h, RADIUS, BG_PANEL, outline=BORDER_MAGENTA)
    draw.rounded_rectangle((RANK_PAD + 24, 20 + 16, RANK_PAD + 30, 20 + top_h - 16), radius=3, fill=GOLD)
    draw.text(
        (RANK_PAD + 46, 20 + top_h // 2 - 24),
        "刮刮乐亏损排行",
        font=nte_font_origin(vw(24)),
        fill=GOLD_HI,
        anchor="lm",
    )
    draw.text(
        (RANK_PAD + 46, 20 + top_h // 2 + 28),
        "仅统计群内塔吉多已登录账号 · 亏损越多排名越高",
        font=nte_font_origin(vw(13)),
        fill=LIGHT_MUTED,
        anchor="lm",
    )

    table_top = 20 + top_h + 14
    _panel(
        canvas,
        RANK_PAD,
        table_top,
        panel_w,
        head_h + len(entries) * row_h + table_bottom_pad,
        vw(10),
        BG_PANEL,
        outline=BORDER_MAGENTA,
    )
    col_x = [
        RANK_PAD + 30,
        RANK_PAD + 120,
        RANK_PAD + 300,
        RANK_PAD + 520,
        RANK_PAD + 680,
        RANK_W - RANK_PAD - 30,
    ]
    header_font = nte_font_origin(vw(12))
    headers = ["排名", "角色", "净盈亏", "投入", "返还", "更新时间"]
    anchors = ["lm", "lm", "lm", "lm", "lm", "rm"]
    for cx, text, anchor in zip(col_x, headers, anchors):
        draw.text((cx, table_top + head_h // 2), text, font=header_font, fill=LIGHT_MUTED, anchor=anchor)
    draw.line(
        [(RANK_PAD + vw(14), table_top + head_h), (RANK_PAD + panel_w - vw(14), table_top + head_h)],
        fill=SEP_COLOR,
        width=1,
    )

    row_font = nte_font_origin(vw(12))
    for index, item in enumerate(entries):
        row_y = table_top + head_h + index * row_h + row_h // 2
        if index % 2 == 1:
            draw.rectangle(
                (
                    RANK_PAD + 12,
                    table_top + head_h + index * row_h,
                    RANK_PAD + panel_w - 12,
                    table_top + head_h + (index + 1) * row_h,
                ),
                fill=BG_ROW_ALT,
            )
        rank = item["rank"]
        rank_color = GOLD_HI
        net = int(item.get("net", 0))
        net_color = COLOR_RED if net < 0 else COLOR_GREEN
        rank_text = str(rank)
        draw.text((col_x[0], row_y), rank_text, font=row_font, fill=rank_color, anchor="lm")
        draw.text((col_x[1], row_y), item.get("role_name", "未知"), font=row_font, fill=COLOR_WHITE, anchor="lm")
        net_text = f"{'+' if net >= 0 else ''}{_fmt_wan(net)}"
        cost_text = _fmt_wan(int(item.get("cost", 0)))
        gain_text = _fmt_wan(int(item.get("gain", 0)))
        draw.text((col_x[2], row_y), net_text, font=row_font, fill=net_color, anchor="lm")
        draw.text((col_x[3], row_y), cost_text, font=row_font, fill=LIGHT_MUTED, anchor="lm")
        draw.text((col_x[4], row_y), gain_text, font=row_font, fill=LIGHT_MUTED, anchor="lm")
        # 更新时间两行：2026/08/11 + 23:15
        updated = str(item.get("updated", ""))
        date_part, _, time_part = updated.partition(" ")
        date_text = date_part.replace("-", "/") if date_part else "--"
        time_text = time_part[:5] if time_part else ""
        draw.text((col_x[5], row_y - 14), date_text, font=row_font, fill=LIGHT_MUTED, anchor="rm")
        draw.text((col_x[5], row_y + 14), time_text, font=row_font, fill=LIGHT_MUTED, anchor="rm")

    draw.text(
        (RANK_W // 2, table_top + head_h + len(entries) * row_h + table_bottom_pad + 26),
        "数据来源：完美世界官方客服系统（kf.wanmei.com）",
        font=nte_font_origin(vw(12)),
        fill=COLOR_MUTED,
        anchor="mt",
    )
    add_footer(canvas)
    return await convert_img(canvas)
