import sys
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from gsuid_core.data_store import get_res_path

MAIN_PATH = get_res_path() / "NTEUID"
sys.path.append(str(MAIN_PATH))

CONFIG_PATH = MAIN_PATH / "config.json"
# 面板
PLAYERINFO_PATH = MAIN_PATH / "playerinfo"

# 角色资料
RESOURCE_PATH = MAIN_PATH / "resource"
STATIC_RESOURCE_PATH = Path(__file__).parents[2] / "resource"
CHAR_META_PATH = STATIC_RESOURCE_PATH / "char_meta.json"

# 别名（用户态可写，与静态 CHAR_META_PATH 分离）
ALIAS_PATH = MAIN_PATH / "alias"
USER_CHAR_ALIAS_PATH = ALIAS_PATH / "char_alias.json"

# 角色
ROLE_PATH = MAIN_PATH / "role"
ROLE_CARD_PATH = ROLE_PATH / "card"
ROLE_ART_PATH = ROLE_PATH / "detail"
ROLE_SKILL_PATH = ROLE_PATH / "skill"
ROLE_CITY_SKILL_PATH = ROLE_PATH / "city_skill"
ROLE_AVATAR_PATH = ROLE_PATH / "avatar"
ROLE_GROUP_PATH = ROLE_PATH / "group"
ROLE_GROUP_BLACK_PATH = ROLE_PATH / "group_black"
ROLE_ELEMENT_PATH = ROLE_PATH / "element"
ROLE_AWAKEN_PATH = ROLE_PATH / "awaken"
ROLE_PROPERTY_PATH = ROLE_PATH / "property"
ROLE_SUIT_DETAIL_PATH = ROLE_PATH / "suit" / "detail"
ROLE_SUIT_DRIVE_PATH = ROLE_PATH / "suit" / "drive"

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


def init_dir():
    for path in [
        MAIN_PATH,
        PLAYERINFO_PATH,
        RESOURCE_PATH,
        OTHER_PATH,
        NOTICE_PATH,
        TEAM_PATH,
        SIGN_CALENDAR_PATH,
        ROLE_PATH,
        ROLE_CARD_PATH,
        ROLE_ART_PATH,
        ROLE_SKILL_PATH,
        ROLE_CITY_SKILL_PATH,
        ROLE_AVATAR_PATH,
        ROLE_GROUP_PATH,
        ROLE_GROUP_BLACK_PATH,
        ROLE_ELEMENT_PATH,
        ROLE_AWAKEN_PATH,
        ROLE_PROPERTY_PATH,
        WEAPON_PATH,
        ROLE_SUIT_DETAIL_PATH,
        ROLE_SUIT_DRIVE_PATH,
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
    ]:
        path.mkdir(parents=True, exist_ok=True)


init_dir()

TEMPLATE_PATH = Path(__file__).parents[1].parent / "templates"
NTE_TEMPLATES = Environment(loader=FileSystemLoader([str(TEMPLATE_PATH)]))
