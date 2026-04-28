from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

from gsuid_core.models import Event
from gsuid_core.utils.image.convert import convert_img
from gsuid_core.utils.image.image_tools import get_event_avatar

from ..utils.image import (
    COLOR_WHITE,
    add_footer,
    get_nte_bg,
    char_img_ring,
    make_nte_role_title,
)
from ..utils.resource.cdn import get_avatar_img
from ..utils.fonts.nte_fonts import nte_font_24
from ..utils.sdk.tajiduo_model import RoleHome, CharacterDetail

REFRESH_TEX = Path(__file__).parent / "texture2d" / "refresh"


async def _build_char_avatars(characters: list[CharacterDetail]) -> dict[str, Image.Image | None]:
    return {ch.id: await get_avatar_img(ch.id) for ch in characters}


async def draw_refresh_img(
    ev: Event,
    role_name: str,
    uid: str,
    home: RoleHome,
    characters: list[CharacterDetail],
    changed_count: int,
):
    user_avatar = await get_event_avatar(ev)
    char_avatars = await _build_char_avatars(characters)

    title = make_nte_role_title(user_avatar, role_name, uid, home.lev)

    rows = max(1, (len(characters) + 6) // 7)
    canvas_h = 246 + (rows - 1) * 290 + 340 + 90
    canvas: Image.Image = get_nte_bg(1680, canvas_h).convert("RGBA")

    canvas.alpha_composite(title, (40, 30))

    title2 = Image.open(REFRESH_TEX / "title2.png").convert("RGBA")
    ImageDraw.Draw(title2).text(
        (60, 22),
        f"角色已刷新完成，本次共刷新 {changed_count} 个角色",
        font=nte_font_24,
        fill=(235, 240, 245),
        anchor="lm",
    )
    canvas.alpha_composite(title2, (1120, 176))

    bg = Image.open(REFRESH_TEX / "char_bg.png").convert("RGBA")
    badge = Image.open(REFRESH_TEX / "badge.png").convert("RGBA")

    for i, char in enumerate(characters):
        row, col = divmod(i, 7)
        cell_x = 40 + col * 227
        cell_y = 246 + row * 290

        cell_bg = bg.copy()

        avatar = char_avatars[char.id]
        if avatar is not None:
            cell_bg.alpha_composite(char_img_ring(avatar, 230), (5, 48))

        char_badge = badge.copy()
        ImageDraw.Draw(char_badge).text(
            (45, 23),
            f"{char.awaken_lev}觉",
            font=nte_font_24,
            fill=COLOR_WHITE,
            anchor="mm",
        )
        cell_bg.alpha_composite(char_badge, (136, 69))

        ImageDraw.Draw(cell_bg).text(
            (121, 292),
            char.name,
            font=nte_font_24,
            fill=COLOR_WHITE,
            anchor="mm",
        )

        canvas.alpha_composite(cell_bg, (cell_x, cell_y))

    add_footer(canvas)
    return await convert_img(canvas)
