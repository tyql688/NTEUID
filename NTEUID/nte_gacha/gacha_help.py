from ..utils.constants import (
    XIAOHEIHE_WEB_URL,
    TAPTAP_BIND_GUIDE_URL,
    TAPTAP_PERSONAL_INFO_URL,
)
from ..nte_config.prefix import nte_prefix


async def draw_gacha_help() -> list[str]:
    p = nte_prefix()

    return [
        "\n".join(
            [
                "1. 塔吉多官方一级源（推荐）",
                "",
                f"登录后直接发送：{p}抽卡记录",
            ]
        ),
        "\n".join(
            [
                "2. TapTap 战绩页",
                "",
                f"① 在 TapTap 绑定异环角色：{TAPTAP_BIND_GUIDE_URL}",
                "",
                f"② 获取 TapTap user_id：{TAPTAP_PERSONAL_INFO_URL}",
                "",
                f"③ 发送：{p}抽卡记录 <user_id>",
                "记录按游戏 UID 合并到本地，重复查询不会重复计数。",
                f"登录同一角色后，发送「{p}抽卡记录」可查看合并结果。",
                "",
                "④ 刷新数据：回到战绩页点击『更新数据』按钮",
            ]
        ),
        "\n".join(
            [
                "3. 小黑盒（pkey 会过期）",
                "",
                f"① 网页登录小黑盒：{XIAOHEIHE_WEB_URL}",
                "",
                "② 按 F12 打开开发者工具 → Application/Storage → Cookies → api.xiaoheihe.cn",
                "   （中文浏览器：应用程序/存储 → Cookie → api.xiaoheihe.cn）",
                "   找到 user_pkey 的值并完整复制",
                "",
                f"③ 发送：{p}抽卡记录 <user_pkey>",
                "记录按游戏 UID 合并到本地，重复查询不会重复计数。",
                f"登录同一角色后，发送「{p}抽卡记录」可查看合并结果。",
            ]
        ),
    ]
