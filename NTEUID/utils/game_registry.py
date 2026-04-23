from __future__ import annotations

from typing import Dict, Optional

from .constants import GAME_ID_HUANTA, GAME_ID_YIHUAN

# 塔吉多旗下参与本插件签到的游戏——新增游戏只在这里加一条即可。
#   - 键：`game_id`
#   - 值：签到开关的 config key；None 表示强制签，不给用户开关
# 注册顺序 = 优先级。第一条是**主游戏**：
#   - `NTEUser.get_active` 默认只看主游戏
#   - 登录时为主游戏自动绑定主角色（塔吉多 bind_role 成就任务）
GAME_SIGN_SWITCHES: Dict[str, Optional[str]] = {
    GAME_ID_YIHUAN: None,
    GAME_ID_HUANTA: "NTESignHuanta",
}

PRIMARY_GAME_ID: str = next(iter(GAME_SIGN_SWITCHES))
