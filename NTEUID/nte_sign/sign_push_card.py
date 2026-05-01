from __future__ import annotations

from datetime import datetime

from PIL import ImageDraw

from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    COLOR_RED,
    COLOR_GREEN,
    COLOR_MUTED,
    COLOR_TITLE,
    COLOR_DIVIDER,
    draw_card,
    add_footer,
    get_nte_bg,
)
from ..utils.fonts.nte_fonts import (
    nte_font_bold,
    nte_font_origin,
)

# 整图：紧凑横幅；显式字面量布局，不算公式（NTE 拼图风格）。
WIDTH = 1080
HEIGHT = 540

EYEBROW_FONT = nte_font_origin(28)
TITLE_FONT = nte_font_bold(64)
DATE_FONT = nte_font_origin(24)
NUM_FONT = nte_font_bold(76)
LABEL_FONT = nte_font_origin(26)


async def draw_sign_push_title(success: int, failed: int) -> bytes | str:
    """群签到推送的 NTE 风格标题图：今日签到完成 + 成功 / 失败计数。"""
    canvas = get_nte_bg(WIDTH, HEIGHT).convert("RGBA")
    draw = ImageDraw.Draw(canvas)

    # 卡片：1000×400，留 70 给底部 footer
    draw_card(draw, (40, 40, 1040, 440))

    # 顶栏：左上 [异环] 自动签到、右上 日期
    draw.text((76, 72), "[异环] 自动签到", font=EYEBROW_FONT, fill=COLOR_MUTED)
    draw.text(
        (1004, 76),
        datetime.now().strftime("%Y-%m-%d"),
        font=DATE_FONT,
        fill=COLOR_TITLE,
        anchor="rt",
    )

    # 大字标题
    draw.text((76, 130), "今日签到任务已完成", font=TITLE_FONT, fill=COLOR_TITLE)

    # 两列数字统计：成功 / 失败
    stats = [
        (str(success), "成功", COLOR_GREEN),
        (str(failed), "失败", COLOR_RED),
    ]

    cell_w = 1000 // len(stats)
    for index, (value, label, color) in enumerate(stats):
        cx = 40 + cell_w * index + cell_w // 2
        draw.text((cx, 264), value, font=NUM_FONT, fill=color, anchor="mt")
        draw.text((cx, 372), label, font=LABEL_FONT, fill=COLOR_MUTED, anchor="mt")
        if index < len(stats) - 1:
            sep_x = 40 + cell_w * (index + 1)
            draw.line([(sep_x, 280), (sep_x, 412)], fill=COLOR_DIVIDER, width=2)

    add_footer(canvas)
    return await convert_img(canvas)
