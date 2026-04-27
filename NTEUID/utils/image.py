import re
import html
import random
import hashlib
from typing import Tuple, Union, Optional
from pathlib import Path
from urllib.parse import quote_plus

from PIL import Image, ImageOps, ImageDraw, ImageFont

from gsuid_core.utils.image.image_tools import crop_center_img
from gsuid_core.utils.download_resource.download_file import download

from .fonts.nte_fonts import nte_font_30, nte_font_42, nte_font_50
from ..utils.resource.RESOURCE_PATH import QR_PATH

ICON = Path(__file__).parent.parent.parent / "ICON.png"
TEXT_PATH = Path(__file__).parent / "texture2d"
CARD_LONG_PATH = TEXT_PATH / "card_long"
FRAME_PATH = TEXT_PATH / "frame"

Color = Union[Tuple[int, int, int], Tuple[int, int, int, int]]
Box = Tuple[int, int, int, int]  # (left, top, right, bottom)
Size = Tuple[int, int]  # (width, height)

COLOR_WHITE = (255, 255, 255)  # 纯白
COLOR_BG = (245, 242, 234)  # 主背景米色 / #F5F2EA
COLOR_PANEL = (255, 253, 248)  # 卡片面板奶白 / #FFFDF8
COLOR_SHADOW = (229, 222, 207)  # 卡片阴影暖灰 / #E5DECF
COLOR_DIVIDER = (231, 223, 209)  # 分隔线米白 / #E7DFD1
COLOR_GRAY = (215, 210, 199)  # 中性灰 / #D7D2C7

COLOR_TITLE = (31, 41, 55)  # 标题深蓝灰 / #1F2937
COLOR_TEXT = (55, 65, 81)  # 正文深灰 / #374151
COLOR_MUTED = (107, 114, 128)  # 弱化灰 / #6B7280
COLOR_SUBTEXT = (229, 237, 242)  # 辅助浅灰 / #E5EDF2
COLOR_DARK = (17, 24, 39)  # 暗色 / #111827
COLOR_NAVY = (47, 72, 88)  # 深海蓝 / #2F4858

COLOR_BLUE = (37, 99, 235)  # 链接/高亮蓝 / #2563EB
COLOR_ORANGE = (245, 158, 11)  # 活动橙 / #F59E0B
COLOR_GREEN = (16, 185, 129)  # 成功绿 / #10B981
COLOR_RED = (239, 68, 68)  # 警示红 / #EF4444

COLOR_OVERLAY = (12, 20, 32, 28)  # 图片暗角 RGBA

DEFAULT_CARD_RADIUS = 22
DEFAULT_LINE_GAP = 8
DEFAULT_ELLIPSIS = "..."

_RICH_TAG_RE = re.compile(r"<[^>]+>")
_RICH_BREAK_RE = re.compile(r"(?<![A-Za-z])rn(?![A-Za-z])")
_SPACE_RE = re.compile(r"[ \t]+")
_BLANK_LINE_RE = re.compile(r"\n{3,}")


def cache_name(*parts: object, ext: str = "png") -> str:
    """按输入生成稳定的缓存文件名（sha1）。"""
    raw = "|".join(str(part) for part in parts)
    return f"{hashlib.sha1(raw.encode('utf-8')).hexdigest()}.{ext}"


async def download_pic_from_url(
    path: Path,
    pic_url: str,
    size: Optional[Size] = None,
    name: Optional[str] = None,
) -> Image.Image:
    path.mkdir(parents=True, exist_ok=True)

    if not name:
        name = pic_url.split("/")[-1]
    _path = path / name
    if not _path.exists():
        await download(pic_url, path, name, tag="[NTE]")

    img = Image.open(_path)
    if size:
        img = img.resize(size)

    return img.convert("RGBA")


async def load_qr_code(url: str, size: int = 220) -> Optional[Image.Image]:
    """用 api.qrserver.com 生成 `url` 的二维码，失败返回 None。"""
    qr_url = f"https://api.qrserver.com/v1/create-qr-code/?size={size}x{size}&data={quote_plus(url)}"
    try:
        image = await download_pic_from_url(QR_PATH, qr_url, name=cache_name("qr", url, size))
    except OSError:
        return None
    return image.convert("RGB").resize((size, size), Image.Resampling.LANCZOS)


def shrink_to_width(image: Image.Image, max_width: int) -> Image.Image:
    """宽超过 `max_width` 才缩放；否则原图返回。"""
    if image.width <= max_width:
        return image
    ratio = max_width / image.width
    return image.resize(
        (int(max_width), int(image.height * ratio)),
        Image.Resampling.LANCZOS,
    )


def rounded_mask(size: Size, radius: int) -> Image.Image:
    """圆角矩形 L 模式遮罩，配合 `canvas.paste(img, pos, mask)` 用。"""
    mask = Image.new("L", size, 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, size[0], size[1]), radius=radius, fill=255)
    return mask


def line_height(font: ImageFont.FreeTypeFont) -> int:
    return sum(font.getmetrics())


def measure_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
) -> Tuple[int, int]:
    left, top, right, bottom = draw.textbbox((0, 0), text, font=font)
    return int(right - left), int(bottom - top)


def draw_card(
    draw: ImageDraw.ImageDraw,
    box: Box,
    *,
    radius: int = DEFAULT_CARD_RADIUS,
    fill: Color = COLOR_PANEL,
    shadow: Optional[Color] = COLOR_SHADOW,
    shadow_offset: int = 8,
) -> None:
    """圆角卡片 + 底部偏移阴影。`shadow=None` 关闭阴影。"""
    left, top, right, bottom = box
    if shadow:
        draw.rounded_rectangle(
            (left, top + shadow_offset, right, bottom + shadow_offset),
            radius=radius,
            fill=shadow,
        )
    draw.rounded_rectangle(box, radius=radius, fill=fill)


def wrap_text(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    max_lines: Optional[int] = None,
    ellipsis: str = DEFAULT_ELLIPSIS,
) -> list[str]:
    """按像素宽度折行；超过 `max_lines` 截断并追加 `ellipsis`。"""
    lines: list[str] = []
    raw_lines = text.splitlines() if text else [""]
    for raw_line in raw_lines:
        current = ""
        for char in raw_line:
            trial = f"{current}{char}"
            width = draw.textbbox((0, 0), trial, font=font)[2]
            if current and width > max_width:
                lines.append(current)
                current = char
            else:
                current = trial
        lines.append(current if current else " ")

    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(" .") + ellipsis
    return lines


def text_block_height(
    line_count: int,
    font: ImageFont.FreeTypeFont,
    *,
    line_gap: int = DEFAULT_LINE_GAP,
) -> int:
    if line_count <= 0:
        return 0
    return line_count * line_height(font) + max(0, line_count - 1) * line_gap


def measure_text_block(
    draw: ImageDraw.ImageDraw,
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
    *,
    line_gap: int = DEFAULT_LINE_GAP,
    max_lines: Optional[int] = None,
) -> Tuple[list[str], int]:
    lines = wrap_text(draw, text, font, max_width, max_lines)
    return lines, text_block_height(len(lines), font, line_gap=line_gap)


def draw_text_block(
    draw: ImageDraw.ImageDraw,
    xy: Tuple[int, int],
    text: str,
    font: ImageFont.FreeTypeFont,
    fill: Color,
    max_width: int,
    *,
    line_gap: int = DEFAULT_LINE_GAP,
    max_lines: Optional[int] = None,
) -> int:
    """绘制多行自动折行文本，返回最后一行底部 y（外部继续排版用）。"""
    x, y = xy
    lines = wrap_text(draw, text, font, max_width, max_lines)
    text_height = line_height(font)
    for index, line in enumerate(lines):
        draw.text((x, y), line, font=font, fill=fill)
        y += text_height
        if index != len(lines) - 1:
            y += line_gap
    return y


def char_img_ring(avatar: Image.Image, size: int) -> Image.Image:
    """角色头像圆框（size×size RGBA）"""
    canvas = Image.new("RGBA", (size, size))
    head = avatar.convert("RGBA").resize((size, size))
    mask = Image.open(TEXT_PATH / "head_mask.png").convert("L").resize((size, size))
    canvas.paste(head, (0, 0), mask)
    ring = Image.open(TEXT_PATH / "head_ring.png").convert("RGBA").resize((size, size))
    canvas.paste(ring, (0, 0), ring)
    return canvas


def make_head_avatar(
    avatar: Image.Image, size: int = 240, avatar_size: int = 200, frame_id: Optional[str] = None
) -> Image.Image:
    """头像 mask 裁圆 + head_ring 内圈 + 随机 texture2d/frame/*.png 外框。
    `size` 是最终画布和外框尺寸；`avatar_size` 是头像直径，比 `size` 小越多、头像离外框越远。"""
    canvas = Image.new("RGBA", (size, size))
    offset = (size - avatar_size) // 2

    head = avatar.convert("RGBA").resize((avatar_size, avatar_size))
    mask = Image.open(TEXT_PATH / "head_mask.png").convert("L").resize((avatar_size, avatar_size))
    canvas.paste(head, (offset, offset), mask)

    ring = Image.open(TEXT_PATH / "head_ring.png").convert("RGBA").resize((avatar_size, avatar_size))
    canvas.paste(ring, (offset, offset), ring)

    frame_path = (
        TEXT_PATH / "frame" / f"{frame_id}.png"
        if frame_id
        else random.choice(list((TEXT_PATH / "frame").glob("*.png")))
    )
    frame = Image.open(frame_path).convert("RGBA").resize((size, size))
    canvas.paste(frame, (0, 0), frame)
    return canvas


def clean_rich_text(text: str) -> str:
    raw = html.unescape(text)
    raw = raw.replace("\\n", "\n").replace("\r\n", "\n").replace("\r", "\n")
    raw = raw.replace('""', '"')
    raw = _RICH_BREAK_RE.sub("\n", raw)
    raw = _RICH_TAG_RE.sub("", raw)
    raw = "\n".join(_SPACE_RE.sub(" ", line).strip() for line in raw.splitlines())
    raw = _BLANK_LINE_RE.sub("\n\n", raw)
    return raw.strip()


def draw_page_header(
    canvas: Image.Image,
    title: str,
    subtitle: str,
    *,
    height: int,
    title_xy: Tuple[int, int],
    subtitle_y: int,
    title_font: ImageFont.FreeTypeFont,
    subtitle_font: ImageFont.FreeTypeFont,
    title_fill: Color = COLOR_WHITE,
    subtitle_fill: Color = COLOR_SUBTEXT,
    base_fill: Color = COLOR_NAVY,
    bg_image: Optional[Image.Image] = None,
) -> None:
    width = canvas.width
    if bg_image is None:
        header = Image.new("RGBA", (width, height), base_fill)
    else:
        header = ImageOps.fit(bg_image.convert("RGBA"), (width, height), method=Image.Resampling.LANCZOS)
    canvas.paste(header, (0, 0))
    canvas.alpha_composite(Image.new("RGBA", (width, height), COLOR_OVERLAY), (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text(title_xy, title, font=title_font, fill=title_fill)
    draw.text((title_xy[0], subtitle_y), subtitle, font=subtitle_font, fill=subtitle_fill)


class SmoothDrawer:
    """通用抗锯齿绘制工具"""

    def __init__(self, scale: int = 4):
        self.scale = scale

    def rounded_rectangle(
        self,
        xy: Union[Tuple[int, int, int, int], Tuple[int, int]],
        radius: int,
        fill: Optional[Color] = None,
        outline: Optional[Color] = None,
        width: int = 0,
        target: Optional[Image.Image] = None,
    ):
        if len(xy) == 4:
            # 边界框坐标 (x0, y0, x1, y1)
            x0, y0, x1, y1 = xy
            w = abs(x1 - x0)
            h = abs(y1 - y0)
            # 如果提供了目标图片，使用边界框的实际坐标
            paste_x, paste_y = min(x0, x1), min(y0, y1)
        elif len(xy) == 2:
            # 尺寸 (width, height) - 向后兼容
            w, h = xy
            paste_x, paste_y = 0, 0
        else:
            raise ValueError(f"xy 参数必须是 2 或 4 个元素的元组，当前为 {len(xy)} 个元素")

        if h <= 0 or w <= 0:
            return

        large = Image.new("RGBA", (w * self.scale, h * self.scale), (0, 0, 0, 0))
        draw = ImageDraw.Draw(large)

        # 绘制
        draw.rounded_rectangle(
            (0, 0, w * self.scale, h * self.scale),
            radius=radius * self.scale,
            fill=fill,
            outline=outline,
            width=width * self.scale,
        )

        result = large.resize((w, h))

        if target is not None:
            target.alpha_composite(result, (paste_x, paste_y))
            return

        return


def get_smooth_drawer(scale: int = 4) -> SmoothDrawer:
    return SmoothDrawer(scale=scale)


def get_nte_bg(w: int, h: int, bg: str = "bg") -> Image.Image:
    img = Image.open(TEXT_PATH / f"{bg}.jpg").convert("RGBA")
    return crop_center_img(img, w, h)


def get_nte_title_bg(width: int, height: int, *, game: str = "yihuan") -> Image.Image:
    """home banner 切到指定尺寸（顶部居中），用作页面顶 banner 底图；
    `game` 选 `yihuan` / `huanta`，对应 `home-yihuan.webp` / `home-huanta.webp`。"""
    image = Image.open(TEXT_PATH / f"home-{game}.webp").convert("RGB")
    return ImageOps.fit(image, (width, height), method=Image.Resampling.LANCZOS, centering=(0.5, 0.0))


def _load_card_long(card_long_id: Optional[str] = None) -> Image.Image:
    if card_long_id:
        path = CARD_LONG_PATH / f"{card_long_id}.png"
    else:
        path = random.choice(list(CARD_LONG_PATH.glob("*.png")))
    return Image.open(path).convert("RGBA")


def make_nte_role_title(
    qq_avatar: Image.Image,
    role_name: str,
    uid: Union[str, int],
    level: Optional[int] = None,
    *,
    frame_id: Optional[str] = None,
    card_long_id: Optional[str] = None,
) -> Image.Image:
    """通用 QQ 头像 + 角色名 + UID (+ 等级) title，返回 1100×216 RGBA。"""
    uid_layer = Image.open(TEXT_PATH / "uid_bg.png").convert("RGBA")
    ImageDraw.Draw(uid_layer).text((385, 145), f"UID {uid}", font=nte_font_30, fill=COLOR_DARK, anchor="mm")

    avatar_block = make_head_avatar(qq_avatar, size=216, avatar_size=198, frame_id=frame_id)

    canvas = Image.new("RGBA", (1100, 216), (0, 0, 0, 0))

    mask = Image.open(TEXT_PATH / "maskB.png").convert("RGBA")
    card_long = _load_card_long(card_long_id).resize((1528, 128), Image.Resampling.LANCZOS)
    banner_layer = Image.new("RGBA", (1100, 199), (0, 0, 0, 0))
    banner_layer.paste(card_long, (-428, 56))
    banner = Image.new("RGBA", (1100, 199), (0, 0, 0, 0))
    banner.paste(banner_layer, (0, 0), mask=mask.split()[3])
    canvas.alpha_composite(banner, (0, 8))

    canvas.alpha_composite(uid_layer, (0, 8))

    ImageDraw.Draw(canvas).text((335, 98), role_name, font=nte_font_50, fill=COLOR_WHITE, anchor="mm")

    canvas.alpha_composite(avatar_block, (0, 0))

    if level is not None:
        level_block = Image.open(TEXT_PATH / "level.png").convert("RGBA")
        ImageDraw.Draw(level_block).text((53, 53), str(level), font=nte_font_42, fill=COLOR_WHITE, anchor="mm")
        canvas.alpha_composite(level_block, (904, 75))

    return canvas


def get_footer():
    return Image.open(TEXT_PATH / "footer.png")


def add_footer(
    img: Image.Image,
    w: int = 0,
    offset_y: int = 0,
    is_invert: bool = False,
):
    footer = Image.open(TEXT_PATH / "footer.png")
    if is_invert:
        r, g, b, a = footer.split()
        rgb_image = Image.merge("RGB", (r, g, b))
        rgb_image = ImageOps.invert(rgb_image.convert("RGB"))
        r2, g2, b2 = rgb_image.split()
        footer = Image.merge("RGBA", (r2, g2, b2, a))

    if w != 0:
        footer = footer.resize(
            (w, int(footer.size[1] * w / footer.size[0])),
        )

    x, y = (
        int((img.size[0] - footer.size[0]) / 2),
        img.size[1] - footer.size[1] - 20 + offset_y,
    )

    img.paste(footer, (x, y), footer)
    return img
