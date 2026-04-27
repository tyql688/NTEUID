import json

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.utils.fonts.fonts import core_font
from gsuid_core.utils.image.convert import convert_img

from .utils import get_post_url, format_post_time, get_post_summary
from ..utils.image import (
    COLOR_BG,
    COLOR_RED,
    COLOR_BLUE,
    COLOR_DARK,
    COLOR_GRAY,
    COLOR_TEXT,
    COLOR_GREEN,
    COLOR_MUTED,
    COLOR_TITLE,
    COLOR_WHITE,
    COLOR_ORANGE,
    COLOR_DIVIDER,
    COLOR_OVERLAY,
    COLOR_SUBTEXT,
    draw_card,
    wrap_text,
    cache_name,
    load_qr_code,
    rounded_mask,
    char_img_ring,
    draw_text_block,
    shrink_to_width,
    get_nte_title_bg,
    download_pic_from_url,
)
from ..nte_config.prefix import nte_prefix
from ..utils.fonts.nte_fonts import nte_font_22, nte_font_24, nte_font_26, nte_font_28, nte_font_38
from ..utils.sdk.tajiduo_model import NoticePost
from ..utils.resource.RESOURCE_PATH import NOTICE_PATH

WIDTH = 1080
PADDING = 36
GRID_GAP = 24
CARD_RADIUS = 22


def _get_column_color(name: str):
    if name == "活动":
        return COLOR_GREEN
    if name == "公告":
        return COLOR_RED
    return COLOR_ORANGE


async def _load_preview(url: str, width: int, height: int) -> Image.Image:
    try:
        image = await download_pic_from_url(NOTICE_PATH, url, name=cache_name("preview", url))
        return ImageOps.fit(image.convert("RGB"), (width, height), method=Image.Resampling.LANCZOS)
    except OSError:
        return Image.new("RGB", (width, height), COLOR_GRAY)


async def _load_detail_image(url: str, max_width: int) -> Image.Image:
    try:
        image = await download_pic_from_url(NOTICE_PATH, url, name=cache_name("detail", url))
    except OSError:
        return Image.new("RGB", (max_width, 320), COLOR_GRAY)
    return shrink_to_width(image.convert("RGB"), max_width)


def _extract_detail_blocks(post: NoticePost) -> list[tuple[str, str]]:
    blocks: list[tuple[str, str]] = []

    def flush_text(parts: list[str]):
        if not parts:
            return
        text = "".join(parts).replace("\xa0", " ")
        for line in text.splitlines():
            line = line.strip()
            if line:
                blocks.append(("text", line))
        parts.clear()

    try:
        payload = json.loads(post.structured_content) if post.structured_content else []
    except json.JSONDecodeError:
        payload = []

    text_parts: list[str] = []
    if isinstance(payload, list):
        for item in payload:
            if not isinstance(item, dict):
                continue
            image = item.get("image")
            if isinstance(image, str):
                flush_text(text_parts)
                blocks.append(("image", image))
                continue
            text = item.get("txt")
            if isinstance(text, str):
                text_parts.append(text)

    flush_text(text_parts)

    if not blocks:
        for line in get_post_summary(post).splitlines():
            line = line.strip()
            if line:
                blocks.append(("text", line))

    if not any(kind == "image" for kind, _ in blocks):
        if post.vods and post.vods[0].cover:
            blocks.insert(0, ("image", post.vods[0].cover))
        elif post.images and post.images[0].url:
            blocks.insert(0, ("image", post.images[0].url))

    return blocks


def _start_detail_page(page_index: int) -> tuple[Image.Image, ImageDraw.ImageDraw, int]:
    page = Image.new("RGB", (WIDTH, 5200), COLOR_BG)
    draw = ImageDraw.Draw(page)
    y = PADDING
    if page_index > 0:
        cont_font = nte_font_22
        draw.text((PADDING, y), f"继续阅读 · 第 {page_index + 1} 页", font=cont_font, fill=COLOR_MUTED)
        y += 44
    return page, draw, y


def _append_page(result_pages: list[Image.Image], page: Image.Image, bottom: int):
    result_pages.append(page.crop((0, 0, WIDTH, bottom + PADDING)))


async def draw_notice_list_img(columns: dict[str, list[tuple[str, str, str, str]]]):
    title_font = core_font(42)
    sub_font = core_font(20)
    id_font = core_font(18)
    col_font = core_font(26)
    subject_font = core_font(24)
    meta_font = core_font(20)
    hint_font = core_font(22)

    grid_width = WIDTH - PADDING * 2
    card_width = (grid_width - GRID_GAP * 2) // 3
    image_height = 148
    card_height = 272

    max_rows = 4
    header_height = 202
    canvas_height = header_height + max_rows * card_height + (max_rows - 1) * GRID_GAP + 112 + PADDING
    canvas = Image.new("RGBA", (WIDTH, canvas_height), COLOR_BG)
    draw = ImageDraw.Draw(canvas)

    canvas.paste(get_nte_title_bg(WIDTH, 152), (0, 0))
    overlay = Image.new("RGBA", (WIDTH, 152), COLOR_OVERLAY)
    canvas.alpha_composite(overlay, (0, 0))
    draw = ImageDraw.Draw(canvas)
    title_right = WIDTH - PADDING
    draw.text((title_right, 34), "异环公告", font=title_font, fill=COLOR_WHITE, anchor="ra")
    draw.text((title_right, 96), "资讯 / 活动 / 公告", font=sub_font, fill=COLOR_SUBTEXT, anchor="ra")

    column_names = ["资讯", "活动", "公告"]
    for col, column_name in enumerate(column_names):
        left = PADDING + col * (card_width + GRID_GAP)
        draw.text((left, 170), column_name, font=col_font, fill=COLOR_TITLE)
        draw.rounded_rectangle((left, 208, left + 72, 214), radius=4, fill=_get_column_color(column_name))

        for row, item in enumerate(columns.get(column_name, [])[:max_rows]):
            post_id, subject, time_text, preview_url = item
            top = 234 + row * (card_height + GRID_GAP)
            right = left + card_width
            bottom = top + card_height

            draw_card(draw, (left, top, right, bottom))

            preview = (
                await _load_preview(preview_url, card_width, image_height)
                if preview_url
                else Image.new("RGB", (card_width, image_height), COLOR_GRAY)
            )
            canvas.paste(preview, (left, top), rounded_mask((card_width, image_height), CARD_RADIUS))

            draw.rounded_rectangle((left + 14, top + 14, left + 122, top + 52), radius=16, fill=COLOR_DARK)
            draw.text((left + 68, top + 33), str(post_id), font=id_font, fill=COLOR_WHITE, anchor="mm")

            text_left = left + 16
            text_top = top + image_height + 16
            text_right = right - 16
            subject_bottom = draw_text_block(
                draw,
                (text_left, text_top),
                subject,
                subject_font,
                COLOR_TITLE,
                text_right - text_left,
                line_gap=6,
                max_lines=3,
            )
            draw.text((text_left, subject_bottom + 10), time_text, font=meta_font, fill=COLOR_MUTED)

    footer_top = header_height + max_rows * card_height + (max_rows - 1) * GRID_GAP + 52
    draw_card(draw, (PADDING, footer_top, WIDTH - PADDING, footer_top + 84), radius=24)
    draw.text(
        (PADDING + 28, footer_top + 28),
        f"发送 {nte_prefix()}公告 + postId 查看详情，例如：{nte_prefix()}公告 184039",
        font=hint_font,
        fill=COLOR_TEXT,
    )

    return await convert_img(canvas)


async def draw_notice_detail_img(post: NoticePost):
    subject = post.subject
    time_text = format_post_time(post.create_time)
    author = post.author_name
    author_avatar = post.author_avatar
    url = get_post_url(post)
    blocks = _extract_detail_blocks(post)
    qr_image = await load_qr_code(url)

    title_font = nte_font_38
    meta_font = nte_font_24
    body_font = nte_font_28
    author_font = nte_font_26
    content_width = WIDTH - PADDING * 2
    page_limit = 5000

    pages: list[Image.Image] = []
    page, draw, y = _start_detail_page(0)
    qr_bottom = y
    qr_left = WIDTH - PADDING
    if author_avatar:
        avatar = await _load_detail_image(author_avatar, 120)
        avatar = ImageOps.fit(avatar, (120, 120), method=Image.Resampling.LANCZOS)
        ring_img = char_img_ring(avatar, 120)
        page.paste(ring_img, (PADDING, y), ring_img)
        draw.text((PADDING + 140, y + 32), author, font=author_font, fill=COLOR_TITLE)
        draw.text((PADDING + 140, y + 68), "官方资讯发布", font=meta_font, fill=COLOR_MUTED)
        y += 146
    else:
        if author:
            draw.text((PADDING, y), author, font=author_font, fill=COLOR_TITLE)
            y += 44
            draw.text((PADDING, y), "官方资讯发布", font=meta_font, fill=COLOR_MUTED)
            y += 54

    if qr_image:
        qr_size = 164
        qr_box_w = qr_size + 20
        qr_box_h = qr_size + 20
        qr_left = WIDTH - PADDING - qr_box_w
        qr_top = PADDING
        qr_bottom = qr_top + qr_box_h
        draw_card(draw, (qr_left, qr_top, qr_left + qr_box_w, qr_bottom), radius=18)
        page.paste(qr_image.resize((qr_size, qr_size), Image.Resampling.LANCZOS), (qr_left + 10, qr_top + 10))

    title_width = (qr_left - 24) - PADDING if qr_image else content_width
    y = draw_text_block(draw, (PADDING, y), subject, title_font, COLOR_TITLE, title_width, line_gap=10)
    y += 20
    draw.text((PADDING, y), f"时间：{time_text}", font=meta_font, fill=COLOR_MUTED)
    y += 38

    y = max(y, qr_bottom + 20)

    draw.line((PADDING, y, WIDTH - PADDING, y), fill=COLOR_DIVIDER, width=2)
    y += 28

    for kind, value in blocks:
        if kind == "text":
            lines = wrap_text(draw, value, body_font, content_width)
            line_height = sum(body_font.getmetrics())
            for line in lines:
                if y + line_height + PADDING > page_limit:
                    _append_page(pages, page, y)
                    page, draw, y = _start_detail_page(len(pages))
                fill = COLOR_BLUE if line.startswith((">>>", "▸", "◆")) else COLOR_TEXT
                draw.text((PADDING, y), line, font=body_font, fill=fill)
                y += line_height + 12
            y += 8
            continue

        image = await _load_detail_image(value, content_width)
        image_x = (WIDTH - image.width) // 2
        crop_top = 0
        while crop_top < image.height:
            remain = page_limit - y - PADDING
            if remain < 200:
                _append_page(pages, page, y)
                page, draw, y = _start_detail_page(len(pages))
                remain = page_limit - y - PADDING

            crop_height = int(min(remain, image.height - crop_top))
            part = image.crop((0, crop_top, image.width, crop_top + crop_height))
            page.paste(part, (image_x, y))
            y += crop_height + 18
            crop_top += crop_height
            if crop_top < image.height:
                _append_page(pages, page, y)
                page, draw, y = _start_detail_page(len(pages))

    _append_page(pages, page, y)

    results = [await convert_img(img) for img in pages]
    return results[0] if len(results) == 1 else results
