from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..utils.msgs import RoleMsg, send_nte_notify
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
        return await send_nte_notify(bot, ev, "名称或别名不能为空")

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, f"角色【{char_name}】不存在，请检查名称")
    char_id = char_name_to_char_id(std_char_name)
    if not char_id:
        return await send_nte_notify(bot, ev, f"角色【{char_name}】不存在，请检查名称")

    user_file = load_user_char_aliases()

    if action == "添加":
        check_new_alias = alias_to_char_name(new_alias)
        if check_new_alias:
            return await send_nte_notify(
                bot,
                ev,
                f"别名【{new_alias}】已被角色【{check_new_alias}】占用",
            )

        user_file.root.setdefault(char_id, []).append(new_alias)
        save_user_char_aliases(user_file)
        load_char_meta()
        return await send_nte_notify(
            bot,
            ev,
            f"成功为角色【{std_char_name}】添加别名【{new_alias}】",
        )

    if action == "删除":
        user_aliases = user_file.root.get(char_id, [])
        if new_alias not in user_aliases:
            return await send_nte_notify(
                bot,
                ev,
                f"别名【{new_alias}】不存在或为预置别名，无法删除",
            )

        user_aliases.remove(new_alias)
        if not user_aliases:
            user_file.root.pop(char_id, None)
        save_user_char_aliases(user_file)
        load_char_meta()
        return await send_nte_notify(
            bot,
            ev,
            f"成功为角色【{std_char_name}】删除别名【{new_alias}】",
        )

    return await send_nte_notify(bot, ev, "无效的操作，请检查操作")


async def run_char_alias_list(bot: Bot, ev: Event, char_name: str) -> None:
    if not char_name:
        return await send_nte_notify(bot, ev, RoleMsg.USAGE_DETAIL)

    std_char_name = alias_to_char_name(char_name)
    if not std_char_name:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    alias_list = alias_to_char_name_list(char_name)
    if not alias_list:
        return await send_nte_notify(bot, ev, RoleMsg.CHAR_NOT_FOUND)

    await send_nte_notify(
        bot,
        ev,
        f"角色【{std_char_name}】别名列表：\n" + "\n".join(alias_list),
    )
