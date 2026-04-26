import json
from typing import Dict
from pathlib import Path

from PIL import Image

from gsuid_core.help.model import PluginHelp
from gsuid_core.help.draw_new_plugin_help import get_new_help

from ..version import NTEUID_version
from ..utils.image import get_footer
from ..nte_config.prefix import NTE_PREFIX

ICON = Path(__file__).parent.parent.parent / "ICON.png"
HELP_DATA = Path(__file__).parent / "help.json"
ICON_PATH = Path(__file__).parent / "icon_path"
TEXT_PATH = Path(__file__).parent / "texture2d"


def get_help_data() -> Dict[str, PluginHelp]:
    with open(HELP_DATA, "r", encoding="utf-8") as file:
        return json.load(file)


plugin_help = get_help_data()


def _maybe(name: str) -> Image.Image | None:
    """`texture2d/{name}` 在则用、缺则回退到 gsuid_core help 框架的 dark 默认贴图。"""
    path = TEXT_PATH / name
    return Image.open(path) if path.exists() else None


async def get_help(pm: int):
    return await get_new_help(
        plugin_name="NTEUID",
        plugin_info={f"v{NTEUID_version}": ""},
        plugin_icon=Image.open(ICON),
        plugin_help=plugin_help,
        plugin_prefix=NTE_PREFIX,
        help_mode="dark",
        banner_bg=_maybe("banner_bg.jpg"),
        banner_sub_text="一切正常，就是异常。",
        help_bg=_maybe("bg.jpg"),
        cag_bg=_maybe("cag_bg.png"),
        item_bg=_maybe("item.png"),
        icon_path=ICON_PATH,
        footer=get_footer(),
        enable_cache=False,
        column=4,
        pm=pm,
    )
