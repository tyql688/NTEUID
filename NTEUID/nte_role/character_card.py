from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageOps, ImageDraw

from gsuid_core.logger import logger
from gsuid_core.utils.image.convert import convert_img

from .score import CharacterScore, EquipmentScore, score_character
from .heartlike import heart_level
from .panel_image import get_character_panel_img
from ..utils.image import (
    COLOR_WHITE,
    COLOR_SUBTEXT,
    SmoothDrawer,
    add_footer,
    get_nte_bg,
    open_texture,
    make_nte_role_title,
)
from ..utils.damage.buffs import enemy_mods, scan_character_buffs
from ..utils.resource.cdn import (
    get_weapon_img,
    get_char_skill_img,
    get_char_detail_img,
    get_char_element_img,
    get_char_property_img,
    get_char_city_skill_img,
    get_char_suit_drive_img,
)
from ..utils.damage.models import ScaleStat, CharacterDamage
from ..utils.damage.profiles import build_member_damage
from ..utils.damage.settings import base_enemy
from ..utils.fonts.nte_fonts import nte_font_origin
from ..utils.sdk.tajiduo_model import (
    CharacterFork,
    CharacterSkill,
    CharacterDetail,
    CharacterProperty,
    CharacterSuitItem,
)

WIDTH = 1100
BODY_TOP = 248
GAP = 28
TEX = Path(__file__).parent / "texture2d" / "character"

ROW_HILITE = (255, 0, 235)
CRIT_COLOR = (255, 184, 120)
ZERO_VALUES = {"", "0", "0%", "0.0", "0.0%"}


def _format_value(value: str) -> str:
    raw = value.strip()
    if raw.endswith("%"):
        try:
            num = float(raw[:-1])
        except ValueError:
            return value
        return f"{num:.1f}%" if num % 1 else f"{num:.0f}%"
    try:
        return str(round(float(raw)))
    except ValueError:
        return value


def _visible_props(props: list[CharacterProperty], limit: int) -> list[CharacterProperty]:
    return [prop for prop in props if prop.name and prop.value.strip() not in ZERO_VALUES][:limit]


def _fit_text(draw: ImageDraw.ImageDraw, text: str, width: int, font) -> str:
    if round(draw.textlength(text, font=font)) <= width:
        return text
    value = text
    while value and round(draw.textlength(f"{value}...", font=font)) > width:
        value = value[:-1]
    return f"{value}..." if value else "..."


async def _prop_icon(prop_id: str, size: int) -> Image.Image | None:
    icon = await get_char_property_img(prop_id)
    return icon.resize((size, size), Image.Resampling.LANCZOS) if icon is not None else None


def _badge(icon: Image.Image, size: int) -> Image.Image:
    ring = open_texture(TEX / "char_ring.png", (size, size))
    ring.alpha_composite(icon.convert("RGBA").resize((size, size), Image.Resampling.LANCZOS))
    return ring


def _fade_mask(size: tuple[int, int], start: int, end: int, *, horizontal: bool = False) -> Image.Image:
    gradient = Image.linear_gradient("L")
    if horizontal:
        gradient = gradient.rotate(90, expand=True)
    gradient = gradient.resize(size)
    return Image.composite(Image.new("L", size, end), Image.new("L", size, start), gradient)


def _custom_panel_art(image: Image.Image) -> Image.Image:
    is_landscape = image.width >= image.height
    panel_size = (WIDTH, 948) if is_landscape else (800, 948)
    portrait_size = (760, 948)

    if is_landscape:
        panel_img = ImageOps.fit(image, panel_size, method=Image.Resampling.LANCZOS)
    else:
        panel_img = Image.new("RGBA", panel_size)
        portrait_img = ImageOps.fit(image, portrait_size, method=Image.Resampling.LANCZOS)
        side_mask = Image.new("L", portrait_size, 255)
        side_mask.paste(_fade_mask((220, portrait_size[1]), 255, 0, horizontal=True), (portrait_size[0] - 220, 0))
        panel_img.alpha_composite(Image.composite(portrait_img, Image.new("RGBA", portrait_size), side_mask))

    panel_mask = Image.new("L", panel_size, 255)
    panel_mask.paste(_fade_mask((panel_size[0], 128), 128, 255), (0, 0))
    panel_mask.paste(_fade_mask((panel_size[0], 96), 255, 0), (0, panel_size[1] - 96))
    return Image.composite(panel_img, Image.new("RGBA", panel_size), panel_mask)


def _grade_img(grade: str | None, size: int) -> Image.Image | None:
    return open_texture(TEX / f"rank_{grade}.png", (size, size)) if grade in {"S", "A", "B"} else None


async def _draw_attrs(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    props: list[CharacterProperty],
    score: CharacterScore | None,
) -> None:
    for index, prop in enumerate(_visible_props(props, 9)):
        x, y = 620, BODY_TOP + 160 + index * 64
        canvas.alpha_composite(open_texture(TEX / "attr_bar.png"), (x, y))
        icon = await _prop_icon(prop.id, 40)
        if icon is not None:
            canvas.alpha_composite(icon, (x + 10, y + 10))
        color = ROW_HILITE if score is not None and score.is_role_prop_effective(prop) else COLOR_WHITE
        draw.text((x + 66, y + 31), prop.name, font=nte_font_origin(28), fill=color, anchor="lm")
        draw.text((x + 414, y + 31), _format_value(prop.value), font=nte_font_origin(34), fill=color, anchor="rm")


async def _draw_skill_item(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    skill: CharacterSkill,
    city: bool = False,
    small: bool = False,
) -> None:
    x, y = xy
    if small:
        layer = Image.new("RGBA", (100, 140), (0, 0, 0, 0))
        await _draw_skill_item(layer, ImageDraw.Draw(layer), (0, 0), skill, city)
        canvas.alpha_composite(layer.resize((72, 101), Image.Resampling.LANCZOS), (x, y))
        return
    size = (100, 140)
    canvas.alpha_composite(open_texture(TEX / "skill_bg.png", size), (x, y))
    if not skill.id:
        icon = None
    elif city:
        icon = await get_char_city_skill_img(skill.id)
    else:
        icon = await get_char_skill_img(skill.id)
    if icon is not None:
        canvas.alpha_composite(icon.convert("RGBA").resize((64, 64)), (x + 18, y + 18))
    canvas.alpha_composite(open_texture(TEX / "skill_fg.png", size), (x, y))
    draw.text((x + size[0] // 2, y + 89), skill.name[:4], font=nte_font_origin(18), fill=COLOR_WHITE, anchor="mm")
    draw.text((x + size[0] // 2, y + 115), f"Lv{skill.level}", font=nte_font_origin(20), fill=COLOR_WHITE, anchor="mm")


async def _draw_skills(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    skills: list[CharacterSkill],
    city_skills: list[CharacterSkill],
) -> None:
    y = BODY_TOP + 735
    active_skills = [skill for skill in skills if skill.name and skill.type != "Passive"][:4]
    passive_skills = [skill for skill in skills if skill.name and skill.type == "Passive"][:2]
    for index, skill in enumerate(active_skills):
        await _draw_skill_item(canvas, draw, (58 + index * 130, y), skill)
    for index, skill in enumerate(passive_skills):
        await _draw_skill_item(canvas, draw, (578 + index * 92, y + 20), skill, small=True)
    for skill in [skill for skill in city_skills if skill.name][:1]:
        await _draw_skill_item(canvas, draw, (762, y), skill, city=True)


def _draw_score(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    score: CharacterScore | None,
) -> None:
    x, y = xy
    canvas.alpha_composite(open_texture(TEX / "score_bg.png"), (x, y))
    canvas.alpha_composite(open_texture(TEX / "score_fg.png"), (x, y))
    rank = _grade_img(score.grade if score is not None else None, 92)
    if rank is not None:
        canvas.alpha_composite(rank, (x + 133, y + 58))
    score_text = "--分" if score is None else f"{score.score}分"
    draw.text((x + 180, y + 218), score_text, font=nte_font_origin(42), fill=COLOR_WHITE, anchor="mm")


async def _draw_weapon(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    fork: CharacterFork,
) -> None:
    x, y = xy
    canvas.alpha_composite(open_texture(TEX / "weapon_bg.png"), (x, y))
    weapon = await get_weapon_img(fork.id)
    if weapon is not None:
        weapon.thumbnail((205, 205), Image.Resampling.LANCZOS)
        canvas.alpha_composite(weapon.convert("RGBA"), (x + 20, y + 12))
    canvas.alpha_composite(open_texture(TEX / "weapon_fg.png"), (x, y))

    name = _fit_text(draw, fork.name, 295, nte_font_origin(36))
    draw.text((x + 318, y + 41), name, font=nte_font_origin(36), fill=COLOR_WHITE, anchor="lm")
    stage = int(fork.slev) if fork.slev.isdigit() else 0
    stage_text = f"{stage}阶"
    stage_w = round(draw.textlength(stage_text, font=nte_font_origin(26))) + 34
    SmoothDrawer().rounded_rectangle(
        (x + 568, y + 23, x + 568 + stage_w, y + 69),
        23,
        fill=(231, 46, 58, 245),
        target=canvas,
    )
    draw.text((x + 568 + stage_w // 2, y + 46), stage_text, font=nte_font_origin(26), fill=COLOR_WHITE, anchor="mm")

    star = open_texture(TEX / "drive_star.png", (34, 34))
    star_none = open_texture(TEX / "drive_star_none.png", (34, 34))
    for index in range(5):
        canvas.alpha_composite(star if index < max(0, min(5, stage)) else star_none, (x + 257 + index * 38, y + 74))

    draw.text((x + 124, y + 224), f"Lv{fork.alev}", font=nte_font_origin(36), fill=COLOR_WHITE, anchor="mm")
    for index, prop in enumerate(_visible_props(fork.properties, 2)):
        px, py = x + 251, y + 125 + index * 66
        canvas.alpha_composite(open_texture(TEX / "weapon_attr_bar.png"), (px, py))
        icon = await _prop_icon(prop.id, 48)
        if icon is not None:
            canvas.alpha_composite(icon, (px + 8, py + 7))
        draw.text((px + 78, py + 31), prop.name, font=nte_font_origin(26), fill=COLOR_WHITE, anchor="lm")
        draw.text(
            (px + 334, py + 31),
            f"+{_format_value(prop.value)}",
            font=nte_font_origin(26),
            fill=COLOR_WHITE,
            anchor="rm",
        )


async def _draw_drive_prop(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    prop: CharacterProperty,
    color: tuple[int, int, int],
    locked: bool = False,
) -> None:
    x, y = xy
    canvas.alpha_composite(open_texture(TEX / "ad_attr_bg.png"), (x, y))
    icon = await _prop_icon(prop.id, 34)
    if icon is not None:
        canvas.alpha_composite(icon, (x + 8, y + 6))
    draw.text(
        (x + 52, y + 24),
        _fit_text(draw, prop.name, 170, nte_font_origin(24)),
        font=nte_font_origin(24),
        fill=color,
        anchor="lm",
    )
    draw.text((x + 306, y + 24), _format_value(prop.value), font=nte_font_origin(24), fill=color, anchor="rm")
    if locked:
        SmoothDrawer().rounded_rectangle((x, y, x + 320, y + 46), 15, fill=(70, 70, 76, 125), target=canvas)


async def _draw_drive(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    item: CharacterSuitItem,
    score: CharacterScore | None,
    item_score: EquipmentScore | None,
) -> None:
    x, y = xy
    canvas.alpha_composite(open_texture(TEX / "ad_bg.png"), (x, y))
    drive = await get_char_suit_drive_img(item.id) if item.id else None
    if drive is not None:
        canvas.alpha_composite(drive.convert("RGBA").resize((128, 128)), (x, y - 2))
    rank = _grade_img(item_score.grade if item_score is not None else None, 48)
    if rank is not None:
        canvas.alpha_composite(rank, (x + 110, y + 62))
    if item_score is not None:
        score_text = f"{item_score.score:.1f}分"
        score_w = max(104, round(draw.textlength(score_text, font=nte_font_origin(24))) + 34)
        SmoothDrawer().rounded_rectangle(
            (x + 158, y + 70, x + 158 + score_w, y + 108),
            19,
            fill=(238, 72, 145, 245),
            target=canvas,
        )
        draw.text((x + 158 + score_w // 2, y + 89), score_text, font=nte_font_origin(24), fill=COLOR_WHITE, anchor="mm")
    draw.text(
        (x + 116, y + 34),
        _fit_text(draw, item.name, 220, nte_font_origin(26)),
        font=nte_font_origin(26),
        fill=COLOR_WHITE,
        anchor="lm",
    )
    cursor = y + 124
    for title, props, limit in (("基础属性", item.main_properties, 2), ("附加属性", item.properties, 4)):
        items = [
            (index, prop) for index, prop in enumerate(props) if prop.name and prop.value.strip() not in ZERO_VALUES
        ][:limit]
        if not items:
            continue
        canvas.alpha_composite(open_texture(TEX / "ad_title_bg.png"), (x + 34, cursor))
        draw.text((x + 130, cursor + 18), title, font=nte_font_origin(24), fill=(25, 25, 25), anchor="mm")
        cursor += 49
        unlocked_subs = item_score.unlocked_subs if item_score is not None else item.lev // 5
        for index, prop in items:
            locked = props is item.properties and index >= unlocked_subs
            if score is None:
                color = COLOR_WHITE
            elif props is item.main_properties:
                color = ROW_HILITE if score.is_main_prop_counted(prop) else COLOR_WHITE
            else:
                is_recommend = score.is_sub_prop_recommended(prop)
                if locked:
                    color = (255, 145, 238) if is_recommend else COLOR_WHITE
                else:
                    color = ROW_HILITE if is_recommend else COLOR_WHITE
            await _draw_drive_prop(canvas, draw, (x + 20, cursor), prop, color, locked)
            cursor += 49


def _compute_damage(character: CharacterDetail) -> CharacterDamage | None:
    """按配置敌人等级算单角色面板伤害（含自身条件增益满覆盖）；异常就跳过伤害区块，不连累整张卡。"""
    try:
        scan = scan_character_buffs(character)
        def_reduction, res_reduction = enemy_mods(scan.enemy_debuffs)
        enemy = base_enemy(def_reduction=def_reduction, res_reduction=res_reduction)
        damage, _ = build_member_damage(character, enemy, [*scan.team_buffs, *scan.self_buffs])
    except (KeyError, ValueError) as error:
        logger.debug(f"[NTE伤害] 跳过面板伤害 char={character.id}: {error!r}")
        return None
    return damage if damage.abilities else None


def _damage_section_height(damage: CharacterDamage) -> int:
    height = 76 + 116 + 36  # 标题栏 + 乘区拆解条 + 列头
    for ability in damage.abilities:
        height += 54 + len(ability.segments) * 40 + 12
    return height


def _draw_damage(
    canvas: Image.Image,
    draw: ImageDraw.ImageDraw,
    top: int,
    damage: CharacterDamage,
    accent: tuple[int, int, int],
) -> None:
    drawer = SmoothDrawer()
    x0, x1 = 20, 1080
    col_pct, col_exp, col_crit = 560, 824, 1060

    drawer.rounded_rectangle((x0, top, x1, top + 64), 16, fill=(*accent, 235), target=canvas)
    draw.text((x0 + 28, top + 32), "伤害测算", font=nte_font_origin(34), fill=COLOR_WHITE, anchor="lm")
    draw.text(
        (x1 - 24, top + 32),
        f"对 {damage.context.enemy.level} 级敌人 · 直伤",
        font=nte_font_origin(22),
        fill=COLOR_WHITE,
        anchor="rm",
    )

    y = top + 76
    ctx = damage.context
    drawer.rounded_rectangle((x0, y, x1, y + 88), 16, fill=(28, 32, 44, 210), target=canvas)
    cells = (
        ("总攻击力", f"{ctx.panel.atk:.0f}"),
        ("增伤区", f"×{ctx.dmg_bonus_mult:.2f}"),
        ("暴击期望", f"×{ctx.crit_expected_mult:.2f}"),
        ("防御区", f"×{ctx.def_mult:.2f}"),
        ("抗性区", f"×{ctx.res_mult:.2f}"),
    )
    cell_w = (x1 - x0) // len(cells)
    for index, (label, value) in enumerate(cells):
        cx = x0 + cell_w * index + cell_w // 2
        draw.text((cx, y + 30), label, font=nte_font_origin(22), fill=COLOR_SUBTEXT, anchor="mm")
        draw.text((cx, y + 60), value, font=nte_font_origin(30), fill=COLOR_WHITE, anchor="mm")

    y += 88 + GAP
    draw.text((52, y + 18), "技能 / 倍率", font=nte_font_origin(22), fill=COLOR_SUBTEXT, anchor="lm")
    draw.text((col_exp, y + 18), "期望", font=nte_font_origin(22), fill=COLOR_SUBTEXT, anchor="rm")
    draw.text((col_crit, y + 18), "暴击", font=nte_font_origin(22), fill=COLOR_SUBTEXT, anchor="rm")
    y += 36

    for ability in damage.abilities:
        drawer.rounded_rectangle((x0, y, x1, y + 48), 12, fill=(*accent, 96), target=canvas)
        draw.text(
            (x0 + 20, y + 24),
            f"{ability.type_name}·{ability.name}",
            font=nte_font_origin(26),
            fill=COLOR_WHITE,
            anchor="lm",
        )
        rotation_note = "  Σ多形态" if ability.combo_form_count > 1 else ""
        draw.text(
            (x1 - 20, y + 24),
            f"Lv{ability.level}  循环期望 {ability.rotation_expected:,.0f}{rotation_note}",
            font=nte_font_origin(22),
            fill=COLOR_WHITE,
            anchor="rm",
        )
        y += 54
        for seg in ability.segments:
            suffix = "" if seg.scale is ScaleStat.ATK else f"·{seg.scale.label}"
            draw.text((52, y + 20), f"{seg.name}{suffix}", font=nte_font_origin(24), fill=COLOR_WHITE, anchor="lm")
            draw.text((col_pct, y + 20), f"{seg.pct:.0f}%", font=nte_font_origin(24), fill=COLOR_SUBTEXT, anchor="rm")
            draw.text(
                (col_exp, y + 20), f"{seg.expected:,.0f}", font=nte_font_origin(26), fill=COLOR_WHITE, anchor="rm"
            )
            draw.text((col_crit, y + 20), f"{seg.crit:,.0f}", font=nte_font_origin(24), fill=CRIT_COLOR, anchor="rm")
            y += 40
        y += 12


async def _draw_character_art(canvas: Image.Image, character_id: str) -> Path | None:
    custom_art = get_character_panel_img(character_id)
    if custom_art is not None:
        original_img_path, custom_art_img = custom_art
        art = _custom_panel_art(custom_art_img)
        canvas.alpha_composite(art, (0 if art.width == WIDTH else -32, BODY_TOP - 48))
        return original_img_path

    art = await get_char_detail_img(character_id)
    if art is not None:
        canvas.alpha_composite(
            art.convert("RGBA").resize((800, 948), Image.Resampling.LANCZOS),
            (-32, BODY_TOP - 48),
        )
    return None


async def draw_character_card_with_original(
    character: CharacterDetail, role_name: str, uid: str, avatar: Image.Image
) -> tuple[bytes, Path | None]:
    suit_items = [*character.suit.core, *character.suit.pie] if character.suit.id else []
    score = score_character(character)
    equipment_scores: tuple[EquipmentScore | None, ...] = (None,) * len(suit_items)
    if score is not None:
        equipment_scores = score.equipment
    drive_rows = (len(suit_items) + 2) // 3
    drive_h = 0 if not suit_items else drive_rows * 554 + (drive_rows - 1) * GAP
    gear_h = 272 if suit_items or character.fork.id else 0
    damage = _compute_damage(character)
    damage_h = _damage_section_height(damage) if damage is not None else 0
    height = (
        BODY_TOP
        + 880
        + (GAP + gear_h if gear_h else 0)
        + (GAP + drive_h if drive_h else 0)
        + (GAP + damage_h if damage_h else 0)
        + 96
    )

    canvas = get_nte_bg(WIDTH, height, bg="bg3")
    original_img_path = await _draw_character_art(canvas, character.id)

    title = make_nte_role_title(avatar, role_name, uid, char_id=character.id).resize(
        (1060, 208), Image.Resampling.LANCZOS
    )
    canvas.alpha_composite(title, (20, 26))
    draw = ImageDraw.Draw(canvas)

    x, y = 620, BODY_TOP + 8
    canvas.alpha_composite(open_texture(TEX / "base_info_bg.png"), (x, y))
    elem = await get_char_element_img(character.element_type.value)
    if elem is not None:
        canvas.alpha_composite(_badge(elem, 44), (x + 8, y + 7))
    draw.text((x + 111, y + 29), f"Lv{character.alev}", font=nte_font_origin(30), fill=COLOR_WHITE, anchor="mm")
    draw.text(
        (x + 176, y + 29),
        _fit_text(draw, character.name, 220, nte_font_origin(44)),
        font=nte_font_origin(44),
        fill=COLOR_WHITE,
        anchor="lm",
    )

    y = BODY_TOP + 75
    canvas.alpha_composite(open_texture(TEX / "banner.png", (300, 81)), (x, y))
    draw.text((x + 105, y + 41), "角色属性", font=nte_font_origin(34), fill=(25, 25, 25), anchor="lm")
    canvas.alpha_composite(open_texture(TEX / "heart.png", (60, 52)), (x + 305, y + 15))
    like = heart_level(character.likeability_lev)
    draw.text((x + 335, y + 41), str(like), font=nte_font_origin(26), fill=COLOR_WHITE, anchor="mm")
    canvas.alpha_composite(open_texture(TEX / "jue.png", (63, 48)), (x + 374, y + 17))
    draw.text((x + 405, y + 41), f"{character.awaken_lev}觉", font=nte_font_origin(26), fill=COLOR_WHITE, anchor="mm")

    await _draw_attrs(canvas, draw, character.properties, score)
    await _draw_skills(canvas, draw, character.skills, character.city_skills)

    cursor = BODY_TOP + 880 + GAP
    if gear_h:
        if suit_items:
            _draw_score(canvas, draw, (18, cursor), score)
        if character.fork.id:
            await _draw_weapon(canvas, draw, (406 if suit_items else 18, cursor), character.fork)
        cursor += gear_h + GAP
    for index, item in enumerate(suit_items):
        await _draw_drive(
            canvas,
            draw,
            (4 + index % 3 * 366, cursor + index // 3 * (554 + GAP)),
            item,
            score,
            equipment_scores[index],
        )

    if damage is not None:
        damage_top = cursor + (drive_h + GAP if suit_items else 0)
        _draw_damage(canvas, draw, damage_top, damage, character.element_type.color)

    add_footer(canvas)
    return await convert_img(canvas), original_img_path
