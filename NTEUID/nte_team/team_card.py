from __future__ import annotations

from pathlib import Path
from dataclasses import dataclass

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.utils.image.convert import convert_img

from ..utils.image import (
    COLOR_WHITE,
    COLOR_OVERLAY,
    COLOR_SUBTEXT,
    vw,
    add_footer,
    cache_name,
    get_nte_bg,
    get_nte_title_bg,
    download_pic_from_url,
)
from ..utils.fonts.nte_fonts import (
    nte_font_22,
    nte_font_42,
    nte_font_origin,
)
from ..utils.sdk.tajiduo_model import TeamRecommendation
from ..utils.resource.RESOURCE_PATH import TEAM_PATH

WIDTH = 1080
PADDING = 36
HEADER_HEIGHT = 152
FOOTER_RESERVE = 80  # 底部给 add_footer 留位（footer 贴底 20px + 自身高 47px + 余量）
TEXTURE_PATH = Path(__file__).parent / "texture2d"

SECTION_GAP = vw(20)
HEADER_IMAGE_GAP = vw(10)
TITLE_SUB_GAP = vw(2)
ICON_TEXT_GAP = vw(2)
ICON_SIZE = vw(18)
TITLE_FONT_SIZE = vw(18)
SUBTITLE_FONT_SIZE = max(10, vw(4))
DESC_FONT_SIZE = vw(13)
DESC_BOX_PAD_X = vw(6)
DESC_BOX_PAD_Y = vw(10)
DESC_BOX_GAP = vw(10)
DESC_LINE_GAP = vw(3)
DESC_RADIUS_SMALL = vw(2)
DESC_RADIUS_LARGE = vw(12)
INTER_REC_GAP = vw(28)
PAGE_PAD_X = vw(15)
CONTENT_WIDTH = WIDTH - PAGE_PAD_X * 2
DESC_TEXT_WIDTH = CONTENT_WIDTH - DESC_BOX_PAD_X * 2

COLOR_DESC_BG = (220, 220, 220)
COLOR_DESC_TEXT = (84, 84, 84)
COLOR_SECTION_TITLE = (240, 240, 245)
COLOR_SUBTITLE_GRAY = (177, 177, 177)
SUBTITLE_TEXT = "CHARACTER ATTRIBUTE"

title_font = nte_font_origin(TITLE_FONT_SIZE)
subtitle_font = nte_font_origin(SUBTITLE_FONT_SIZE)
desc_font = nte_font_origin(DESC_FONT_SIZE)

DESC_LINE_HEIGHT = sum(desc_font.getmetrics())
SECTION_HEADER_HEIGHT = max(
    ICON_SIZE,
    sum(title_font.getmetrics()) + TITLE_SUB_GAP + sum(subtitle_font.getmetrics()),
)


def _load_section_icon(path: Path) -> Image.Image:
    """官方图标是浅色主题下的深色版本；nte 暗底上整体反 RGB（保留 alpha）后再用。"""
    image = Image.open(path).convert("RGBA").resize((ICON_SIZE, ICON_SIZE))
    r, g, b, a = image.split()
    rgb = ImageOps.invert(Image.merge("RGB", (r, g, b)))
    return Image.merge("RGBA", (*rgb.split(), a))


ICON_STAR = _load_section_icon(TEXTURE_PATH / "section_icon_star.png")
ICON_CHEST = _load_section_icon(TEXTURE_PATH / "section_icon_chest.png")

_IMAGE_SECTIONS: tuple[tuple[str, Image.Image], ...] = (
    ("角色卡片", ICON_STAR),
    ("配队推荐", ICON_STAR),
    ("异能加点", ICON_STAR),
    ("弧盘推荐", ICON_CHEST),
    ("空幕推荐", ICON_CHEST),
)


@dataclass(slots=True)
class Section:
    title: str
    icon: Image.Image
    image: Image.Image | None = None
    desc_lines: list[str] | None = None

    @property
    def body_height(self) -> int:
        if self.image is not None:
            return self.image.height
        assert self.desc_lines is not None
        return _desc_box_height(len(self.desc_lines))


def _desc_box_height(line_count: int) -> int:
    text_h = line_count * DESC_LINE_HEIGHT + max(0, line_count - 1) * DESC_LINE_GAP
    return text_h + DESC_BOX_PAD_Y * 2 + DESC_BOX_GAP


def _fit_to_width(image: Image.Image, width: int) -> Image.Image:
    """官方 `w-full` 等价：等比缩放到目标宽度（无论原图更大或更小）。"""
    if image.width == width:
        return image
    ratio = width / image.width
    return image.resize((width, int(image.height * ratio)), Image.Resampling.LANCZOS)


def _wrap_text(draw: ImageDraw.ImageDraw, text: str, max_width: int) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        current = ""
        for ch in raw_line:
            trial = f"{current}{ch}"
            if current and draw.textlength(trial, font=desc_font) > max_width:
                lines.append(current)
                current = ch
            else:
                current = trial
        lines.append(current)
    return lines


async def _load_section_image(url: str) -> Image.Image | None:
    try:
        image = await download_pic_from_url(TEAM_PATH, url, name=cache_name("team-section", url))
    except OSError:
        return None
    return _fit_to_width(image.convert("RGBA"), CONTENT_WIDTH)


async def _prepare_sections(
    rec: TeamRecommendation,
    measure_draw: ImageDraw.ImageDraw,
) -> list[Section]:
    sections: list[Section] = []
    for index, url in enumerate(rec.imgs[: len(_IMAGE_SECTIONS)]):
        title, icon = _IMAGE_SECTIONS[index]
        image = await _load_section_image(url)
        if image is None:
            continue
        sections.append(Section(title=title, icon=icon, image=image))
    if rec.desc:
        sections.append(
            Section(
                title="攻略详情",
                icon=ICON_CHEST,
                desc_lines=_wrap_text(measure_draw, rec.desc, DESC_TEXT_WIDTH),
            )
        )
    return sections


def _recommendation_height(sections: list[Section]) -> int:
    if not sections:
        return 0
    base = SECTION_HEADER_HEIGHT + HEADER_IMAGE_GAP
    return sum(base + section.body_height for section in sections) + (len(sections) - 1) * SECTION_GAP


def _draw_section_header(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    section: Section,
    xy: tuple[int, int],
) -> None:
    """[icon | 中文标题 / CHARACTER ATTRIBUTE]，anchor='lt' 让文字与图标顶对齐。"""
    x, y = xy
    canvas.alpha_composite(section.icon, (x, y))
    text_x = x + ICON_SIZE + ICON_TEXT_GAP
    draw.text((text_x, y), section.title, font=title_font, fill=COLOR_SECTION_TITLE, anchor="lt")
    title_bottom = draw.textbbox((text_x, y), section.title, font=title_font, anchor="lt")[3]
    draw.text(
        (text_x, title_bottom + TITLE_SUB_GAP),
        SUBTITLE_TEXT,
        font=subtitle_font,
        fill=COLOR_SUBTITLE_GRAY,
        anchor="lt",
    )


def _asymmetric_rounded_mask(
    size: tuple[int, int],
    radii: tuple[int, int, int, int],
) -> Image.Image:
    """Per-corner radii: (top-left, top-right, bottom-right, bottom-left)，对应 CSS 简写顺序。"""
    w, h = size
    tl, tr, br, bl = radii
    mask = Image.new("L", (w, h), 0)
    d = ImageDraw.Draw(mask)
    d.rectangle((0, 0, w, h), fill=255)
    if tl > 0:
        d.rectangle((0, 0, tl, tl), fill=0)
        d.pieslice((0, 0, tl * 2, tl * 2), 180, 270, fill=255)
    if tr > 0:
        d.rectangle((w - tr, 0, w, tr), fill=0)
        d.pieslice((w - tr * 2, 0, w, tr * 2), 270, 360, fill=255)
    if br > 0:
        d.rectangle((w - br, h - br, w, h), fill=0)
        d.pieslice((w - br * 2, h - br * 2, w, h), 0, 90, fill=255)
    if bl > 0:
        d.rectangle((0, h - bl, bl, h), fill=0)
        d.pieslice((0, h - bl * 2, bl * 2, h), 90, 180, fill=255)
    return mask


def _draw_desc_box(
    canvas: Image.Image,
    desc_lines: list[str],
    xy: tuple[int, int],
) -> None:
    x, y = xy
    text_h = len(desc_lines) * DESC_LINE_HEIGHT + max(0, len(desc_lines) - 1) * DESC_LINE_GAP
    box_w = CONTENT_WIDTH
    box_h = text_h + DESC_BOX_PAD_Y * 2
    fill = Image.new("RGBA", (box_w, box_h), COLOR_DESC_BG + (255,))
    mask = _asymmetric_rounded_mask(
        (box_w, box_h),
        (DESC_RADIUS_SMALL, DESC_RADIUS_LARGE, DESC_RADIUS_SMALL, DESC_RADIUS_LARGE),
    )
    canvas.paste(fill, (x, y), mask)
    text_draw = ImageDraw.Draw(canvas)
    text_y = y + DESC_BOX_PAD_Y
    for line in desc_lines:
        text_draw.text((x + DESC_BOX_PAD_X, text_y), line, font=desc_font, fill=COLOR_DESC_TEXT)
        text_y += DESC_LINE_HEIGHT + DESC_LINE_GAP


def _draw_sections(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    sections: list[Section],
    y: int,
) -> int:
    for index, section in enumerate(sections):
        if index > 0:
            y += SECTION_GAP
        _draw_section_header(canvas, draw, section, (PAGE_PAD_X, y))
        y += SECTION_HEADER_HEIGHT + HEADER_IMAGE_GAP
        if section.image is not None:
            image_x = PAGE_PAD_X + (CONTENT_WIDTH - section.image.width) // 2
            canvas.alpha_composite(section.image, (image_x, y))
            y += section.image.height
        else:
            assert section.desc_lines is not None
            _draw_desc_box(canvas, section.desc_lines, (PAGE_PAD_X, y))
            y += _desc_box_height(len(section.desc_lines))
    return y


async def draw_team_img(
    recommendations: list[TeamRecommendation],
    role_name: str,
):
    measure_draw = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    sections_per_rec = [await _prepare_sections(rec, measure_draw) for rec in recommendations]

    body_height = (
        sum(_recommendation_height(secs) for secs in sections_per_rec)
        + max(0, len(sections_per_rec) - 1) * INTER_REC_GAP
    )
    total_height = HEADER_HEIGHT + PADDING + body_height + FOOTER_RESERVE
    canvas = get_nte_bg(WIDTH, total_height).convert("RGBA")
    canvas.paste(get_nte_title_bg(WIDTH, HEADER_HEIGHT), (0, 0))
    canvas.alpha_composite(Image.new("RGBA", (WIDTH, HEADER_HEIGHT), COLOR_OVERLAY), (0, 0))
    draw = ImageDraw.Draw(canvas)
    title_right = WIDTH - PADDING
    draw.text((title_right, 34), "异环配队", font=nte_font_42, fill=COLOR_WHITE, anchor="ra")
    draw.text((title_right, 96), f"{role_name}  ·  官方推荐", font=nte_font_22, fill=COLOR_SUBTEXT, anchor="ra")

    y = HEADER_HEIGHT + PADDING
    for index, sections in enumerate(sections_per_rec):
        if index > 0:
            y += INTER_REC_GAP
        y = _draw_sections(canvas, draw, sections, y)

    add_footer(canvas)
    return await convert_img(canvas)
