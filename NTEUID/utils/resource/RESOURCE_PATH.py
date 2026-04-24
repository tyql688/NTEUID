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

# 其他
OTHER_PATH = MAIN_PATH / "other"
NOTICE_PATH = OTHER_PATH / "notice"
TEAM_PATH = OTHER_PATH / "team"
SIGN_RECORD_PATH = OTHER_PATH / "sign_record"
QR_PATH = OTHER_PATH / "qr"


def init_dir():
    for path in [
        MAIN_PATH,
        PLAYERINFO_PATH,
        RESOURCE_PATH,
        ROLE_AVATAR_PATH,
        OTHER_PATH,
        NOTICE_PATH,
        TEAM_PATH,
        SIGN_RECORD_PATH,
        ROLE_PATH,
        ROLE_CARD_PATH,
        ROLE_ART_PATH,
        ROLE_SKILL_PATH,
        ROLE_CITY_SKILL_PATH,
        QR_PATH,
        ALIAS_PATH,
    ]:
        path.mkdir(parents=True, exist_ok=True)


init_dir()

TEMPLATE_PATH = Path(__file__).parents[1].parent / "templates"
NTE_TEMPLATES = Environment(loader=FileSystemLoader([str(TEMPLATE_PATH)]))
