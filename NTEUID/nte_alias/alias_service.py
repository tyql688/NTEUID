from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.msgs import AliasMsg, send_nte_notify
from ..utils.name_convert import (
    load_char_meta,
    alias_to_char_name,
    char_name_to_char_id,
    load_user_char_aliases,
    save_user_char_aliases,
    alias_to_char_name_list,
)


async def run_char_alias_action(
    bot: Bot,
    ev: Event,
    action: str,
    char_name: str,
    new_alias: str,
) -> None:
    if not char_name or not new_alias:
        return await send_nte_notify(bot, ev, AliasMsg.EMPTY_NAME_OR_ALIAS)

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, AliasMsg.CHAR_NOT_FOUND.format(char_name=char_name))
    char_id = char_name_to_char_id(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, AliasMsg.CHAR_NOT_FOUND.format(char_name=char_name))

    user_file = load_user_char_aliases()

    if action == "添加":
        check_new_alias = alias_to_char_name(new_alias)
        if check_new_alias:
            return await send_nte_notify(
                bot,
                ev,
                AliasMsg.ALIAS_IN_USE.format(alias=new_alias, char_name=check_new_alias),
            )

        user_file.root.setdefault(char_id, []).append(new_alias)
        save_user_char_aliases(user_file)
        load_char_meta()
        return await send_nte_notify(
            bot,
            ev,
            AliasMsg.ADD_SUCCESS.format(char_name=std_char_name, alias=new_alias),
        )

    if action == "删除":
        user_aliases = user_file.root.get(char_id, [])
        if new_alias not in user_aliases:
            return await send_nte_notify(
                bot,
                ev,
                AliasMsg.ALIAS_NOT_REMOVABLE.format(alias=new_alias),
            )

        user_aliases.remove(new_alias)
        if not user_aliases:
            user_file.root.pop(char_id, None)
        save_user_char_aliases(user_file)
        load_char_meta()
        return await send_nte_notify(
            bot,
            ev,
            AliasMsg.DEL_SUCCESS.format(char_name=std_char_name, alias=new_alias),
        )

    return await send_nte_notify(bot, ev, AliasMsg.INVALID_ACTION)


async def run_char_alias_list(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, AliasMsg.usage_list())

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, AliasMsg.CHAR_NOT_FOUND.format(char_name=char_name))

    alias_list = alias_to_char_name_list(char_name)
    if not alias_list:
        return await send_nte_notify(bot, ev, AliasMsg.CHAR_NOT_FOUND.format(char_name=char_name))

    await send_nte_notify(
        bot,
        ev,
        f"角色【{std_char_name}】别名列表：\n" + "\n".join(alias_list),
    )
