import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "NTEUID"
sys.path.append(str(MAIN_PATH))

CONFIG_PATH = MAIN_PATH / "config.json"

# 角色资料
RESOURCE_PATH = MAIN_PATH / "resource"
STATIC_RESOURCE_PATH = Path(__file__).parents[2] / "resource"
CHAR_META_PATH = STATIC_RESOURCE_PATH / "char_meta.json"
FORK_META_PATH = STATIC_RESOURCE_PATH / "fork_meta.json"
HEART_PATH = STATIC_RESOURCE_PATH / "heart.json"
GUIDE_PATH = STATIC_RESOURCE_PATH / "guide"
CATALOG_PATH = STATIC_RESOURCE_PATH / "catalog"
CATALOG_CHAR_PATH = CATALOG_PATH / "char"
CATALOG_FORK_PATH = CATALOG_PATH / "fork"
SCORING_PATH = STATIC_RESOURCE_PATH / "scoring"

# 别名（用户态可写，与静态 *_META_PATH 分离）
ALIAS_PATH = MAIN_PATH / "alias"
USER_CHAR_ALIAS_PATH = ALIAS_PATH / "char_alias.json"
USER_FORK_ALIAS_PATH = ALIAS_PATH / "fork_alias.json"

# 玩家存档级（role）：主页卡背景
ROLE_PATH = MAIN_PATH / "role"
ROLE_CARD_PATH = ROLE_PATH / "card"

# 可玩角色级（character）：CDN 端路径都叫 character/...，物理目录复用 role/ 不动
CHAR_ART_PATH = ROLE_PATH / "detail"
CHAR_SKILL_PATH = ROLE_PATH / "skill"
CHAR_CITY_SKILL_PATH = ROLE_PATH / "city_skill"
CHAR_AVATAR_PATH = ROLE_PATH / "avatar"
CHAR_GROUP_PATH = ROLE_PATH / "group"
CHAR_GROUP_BLACK_PATH = ROLE_PATH / "group_black"
CHAR_ELEMENT_PATH = ROLE_PATH / "element"
CHAR_AWAKEN_PATH = ROLE_PATH / "awaken"
CHAR_PROPERTY_PATH = ROLE_PATH / "property"
CHAR_SUIT_DETAIL_PATH = ROLE_PATH / "suit" / "detail"
CHAR_SUIT_DRIVE_PATH = ROLE_PATH / "suit" / "drive"

# 武器（弧盘）
WEAPON_PATH = MAIN_PATH / "weapon"

# 车辆
VEHICLE_PATH = MAIN_PATH / "vehicle"
VEHICLE_MODEL_PATH = VEHICLE_PATH / "model"
VEHICLE_WIDE_PATH = VEHICLE_PATH / "wide"

# 区域
AREA_PATH = MAIN_PATH / "area"
AREA_WIDE_PATH = AREA_PATH / "wide"
AREA_SMALL_PATH = AREA_PATH / "small"
AREA_TYPE_PATH = AREA_PATH / "type"

# 成就
ACHIEVEMENT_PATH = MAIN_PATH / "achievement"

# 房产
REALESTATE_PATH = MAIN_PATH / "realestate"
REALESTATE_DETAIL_PATH = REALESTATE_PATH / "detail"
REALESTATE_FURNITURE_PATH = REALESTATE_PATH / "fdetail"

# 其他
OTHER_PATH = MAIN_PATH / "other"
NOTICE_PATH = OTHER_PATH / "notice"
TEAM_PATH = OTHER_PATH / "team"
SIGN_CALENDAR_PATH = OTHER_PATH / "sign_calendar"
QR_PATH = OTHER_PATH / "qr"

# 自定义
CUSTOM_PATH = MAIN_PATH / "custom"
ROLE_PANEL_PATH = CUSTOM_PATH / "panel"


def init_dir():
    for path in [
        MAIN_PATH,
        RESOURCE_PATH,
        OTHER_PATH,
        NOTICE_PATH,
        TEAM_PATH,
        SIGN_CALENDAR_PATH,
        ROLE_PATH,
        ROLE_CARD_PATH,
        CHAR_ART_PATH,
        CHAR_SKILL_PATH,
        CHAR_CITY_SKILL_PATH,
        CHAR_AVATAR_PATH,
        CHAR_GROUP_PATH,
        CHAR_GROUP_BLACK_PATH,
        CHAR_ELEMENT_PATH,
        CHAR_AWAKEN_PATH,
        CHAR_PROPERTY_PATH,
        WEAPON_PATH,
        CHAR_SUIT_DETAIL_PATH,
        CHAR_SUIT_DRIVE_PATH,
        VEHICLE_PATH,
        VEHICLE_MODEL_PATH,
        VEHICLE_WIDE_PATH,
        AREA_PATH,
        AREA_WIDE_PATH,
        AREA_SMALL_PATH,
        AREA_TYPE_PATH,
        ACHIEVEMENT_PATH,
        REALESTATE_PATH,
        REALESTATE_DETAIL_PATH,
        REALESTATE_FURNITURE_PATH,
        QR_PATH,
        ALIAS_PATH,
        CUSTOM_PATH,
        ROLE_PANEL_PATH,
    ]:
        path.mkdir(parents=True, exist_ok=True)


init_dir()

TEMPLATE_PATH = Path(__file__).parents[1].parent / "templates"
NTE_TEMPLATES = Environment(loader=FileSystemLoader([str(TEMPLATE_PATH)]))
