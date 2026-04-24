from pydantic import BaseModel, RootModel, ConfigDict, ValidationError

from gsuid_core.logger import logger

from .resource.RESOURCE_PATH import CHAR_META_PATH, USER_CHAR_ALIAS_PATH


class CharMeta(BaseModel):
    model_config = ConfigDict(extra="ignore")
    name: str = ""
    aliases: list[str] = []
    avatar: str = ""


class CharMetaFile(RootModel[dict[str, CharMeta]]):
    pass


class UserCharAliasFile(RootModel[dict[str, list[str]]]):
    pass


char_alias_data: dict[str, list[str]] = {}
char_id_to_name_data: dict[str, str] = {}
char_id_to_avatar_data: dict[str, str] = {}


def _load_char_meta_file() -> CharMetaFile:
    return CharMetaFile.model_validate_json(CHAR_META_PATH.read_text(encoding="utf-8"))


def load_user_char_aliases() -> UserCharAliasFile:
    if not USER_CHAR_ALIAS_PATH.exists():
        return UserCharAliasFile(root={})
    try:
        return UserCharAliasFile.model_validate_json(USER_CHAR_ALIAS_PATH.read_text(encoding="utf-8"))
    except ValidationError as e:
        logger.warning(f"[NTEUID] {USER_CHAR_ALIAS_PATH} 解析失败，已忽略用户态别名: {e}")
        return UserCharAliasFile(root={})


def save_user_char_aliases(model: UserCharAliasFile) -> None:
    USER_CHAR_ALIAS_PATH.write_text(
        model.model_dump_json(indent=2) + "\n",
        encoding="utf-8",
    )


def load_char_meta() -> None:
    global char_alias_data, char_id_to_name_data, char_id_to_avatar_data

    char_alias_data = {}
    char_id_to_name_data = {}
    char_id_to_avatar_data = {}

    user_aliases = load_user_char_aliases().root

    for char_id, meta in _load_char_meta_file().root.items():
        if not meta.name:
            continue

        char_id_to_name_data[char_id] = meta.name
        if meta.avatar:
            char_id_to_avatar_data[char_id] = meta.avatar

        aliases: list[str] = []
        for alias in [*meta.aliases, *user_aliases.get(char_id, []), meta.name]:
            if not alias or alias in aliases:
                continue
            aliases.append(alias)
        if meta.name not in char_alias_data:
            char_alias_data[meta.name] = aliases


load_char_meta()


def alias_to_char_name(char_name: str | None) -> str | None:
    if not char_name:
        return None
    for name, aliases in char_alias_data.items():
        if char_name in name or char_name in aliases:
            return name
    return None


def alias_to_char_name_list(char_name: str) -> list[str]:
    for name, aliases in char_alias_data.items():
        if char_name in name or char_name in aliases:
            return aliases
    return []


def char_name_to_char_id(char_name: str | None) -> str | None:
    char_name = alias_to_char_name(char_name)
    if not char_name:
        return None
    for char_id, name in char_id_to_name_data.items():
        if name == char_name:
            return char_id
    return None


def alias_to_char_id(char_name: str | None) -> str:
    return char_name_to_char_id(char_name) or ""


def char_id_to_avatar_url(char_id: str) -> str:
    return char_id_to_avatar_data.get(char_id, "")
