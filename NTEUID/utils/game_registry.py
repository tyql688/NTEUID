from __future__ import annotations

from .constants import GAME_ID_HUANTA, GAME_ID_YIHUAN

# 塔吉多旗下参与本插件签到的游戏——新增游戏只在这里加一条即可。
#   - 键：`game_id`
#   - 值：签到开关的 config key；None 表示强制签，不给用户开关
# 注册顺序 = 优先级。第一条是**主游戏**：
#   - `NTEUser.get_active` 默认只看主游戏
#   - 登录时为主游戏自动绑定主角色（塔吉多 bind_role 成就任务）
GAME_SIGN_SWITCHES: dict[str, str | None] = {
    GAME_ID_YIHUAN: None,
    GAME_ID_HUANTA: "NTESignHuanta",
}

PRIMARY_GAME_ID: str = next(iter(GAME_SIGN_SWITCHES))

GAME_LABELS: dict[str, str] = {
    GAME_ID_YIHUAN: "异环",
    GAME_ID_HUANTA: "幻塔",
}

# 顶部 banner 资源 key —— `utils/texture2d/home-{key}.webp`
GAME_BANNER_KEYS: dict[str, str] = {
    GAME_ID_YIHUAN: "yihuan",
    GAME_ID_HUANTA: "huanta",
}
