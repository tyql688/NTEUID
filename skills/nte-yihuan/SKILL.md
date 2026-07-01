---
name: nte-yihuan
description: 异环 yh YH nte NTE NTEUID 环 — 用户要查账号面板、角色面板、练度 box、体力、探索、成就、房产、载具、攻略、配队、图鉴、排行、签到、公告、兑换码、抽卡记录、登录绑定解绑换号时，先 load_skill 阅读本说明。说明型 skill，不含 scripts。
version: 0.1.0
plugin: NTEUID
---

# AI 工具

这些名字是 `ai_tools`，不是 skill script；不要用 `run_skill_script` 调用它们。

## 面板类

- 账号面板：调用 AI 工具 `nte_account`
  触发：我的信息 / 个人主页 / uid / 我的号 / 账号
- 角色面板：调用 AI 工具 `nte_character`，参数 char_name
  触发：xx面板 / xx装备 / xx词条 / xx评分 / xx伤害 / 看看xx练了没 / 帮我看看xx
- 练度面板：调用 AI 工具 `nte_box`
  触发：box / 全角色练度 / 练度统计 / 该练谁 / 角色列表
- 体力：调用 AI 工具 `nte_stamina`
  触发：体力 / 树脂 / 精力 / 本性像素 / 都市活力 / 剩多少体力
- 刷新面板：调用 AI 工具 `nte_refresh`
  触发：刷新面板 / 重新获取 / 更新数据
- 探索：调用 AI 工具 `nte_explore`
  触发：探索度 / 地图探索 / 区域进度 / 探索率
- 成就：调用 AI 工具 `nte_achievement`
  触发：成就进度 / 成就数量 / 成就列表 / 成就做了多少
- 房产：调用 AI 工具 `nte_realestate`
  触发：房产 / 房屋 / 住宅 / 地产 / 家园
- 载具：调用 AI 工具 `nte_vehicle`
  触发：载具 / 车辆 / 交通工具 / 车 / 摩托车 / 坐骑

## 资料类

- 角色攻略：调用 AI 工具 `nte_guide`，参数 char_name
  触发：xx攻略 / 养成图 / 配装攻略 / 怎么练 / 怎么养 / 培养建议
- 图鉴：调用 AI 工具 `nte_catalog`，参数 name
  触发：图鉴 / 角色图鉴 / 武器图鉴 / 百科 / 信息卡
- 配队：调用 AI 工具 `nte_team`，参数 char_name
  触发：配队 / 阵容 / 队伍推荐 / 组队 / 和谁组队
- 别名查询：调用 AI 工具 `nte_alias`，参数 name
  触发：xx别名 / xx有哪些名字 / xx又叫什么

## 排行类

- 本群排行：调用 AI 工具 `nte_group_rank`，参数 char_name
  触发：本群排行 / 本群评分 / 群内谁最高
- Bot排行：调用 AI 工具 `nte_bot_rank`，参数 char_name
  触发：全 bot 排行 / 跨群排行 / 全服排行
- 最强面板：调用 AI 工具 `nte_strongest`，参数 char_name 和 bot_scope
  触发：最强xx / 最高评分 / 天花板面板
- 最强排行：调用 AI 工具 `nte_strongest_board`，参数 bot_scope
  触发：最强排行 / 各角色最高评分榜 / 战力榜

## 日常类

- 签到：调用 AI 工具 `nte_sign`
  触发：签到 / 每日签到 / 打卡
- 签到日历：调用 AI 工具 `nte_sign_calendar`
  触发：签到日历 / 签到奖励 / 月签进度 / 签到记录
- 公告：调用 AI 工具 `nte_notice`
  触发：公告 / 最新公告 / 游戏通知 / 更新公告 / 活动公告
- 兑换码：调用 AI 工具 `nte_codes`
  触发：兑换码 / 礼包码 / cdk / code / 激活码
- 抽卡记录：调用 AI 工具 `nte_gacha`，参数 query
  触发：抽卡记录 / 抽卡统计 / 出金记录 / 抽了多少 / 保底

## 账号类

- 登录：调用 AI 工具 `nte_login`
  触发：登录 / 绑定账号 / 绑定异环 / 绑定塔吉多 / 怎么登录 / 怎么绑号
- 查看绑定：调用 AI 工具 `nte_bindings`
  触发：查看绑定 / 查看账号 / 绑了几个号 / 有哪些账号 / 我的账号
- 切换账号：调用 AI 工具 `nte_switch`，参数 target（可选）
  触发：切换账号 / 换号 / 切号
- 退出登录：调用 AI 工具 `nte_logout`，参数 all_accounts（可选）
  触发：退出登录 / 登出 / 解绑 / 注销 / 退出全部登录
- 帮助：调用 AI 工具 `nte_help`
  触发：帮助 / 怎么用 / 有什么功能 / 能做什么 / 功能列表 / 命令列表

# 与 nte-everness 的边界（硬性）

- **本 skill 负责**：用户账号数据、面板图片、练度、体力、签到、抽卡记录、排行、攻略图、配队推荐、登录绑定。
- **nte-everness 负责**：公开资料查询 — 角色详情/技能/背景/生日/CV/基础属性、活动日历、异能环合、驱动块、弧盘、道具来源。
- 互斥规则：
  - "攻略 / 配装 / 养成推荐" → `nte_guide`（本 skill）
  - "技能描述 / 背景 / 生日 / CV / 基础属性" → 引导到 `nte-everness` 的 `everness_character`
  - "活动日历 / 活动时间" → `nte-everness` 的 `everness_activity`
  - "公告 / 最新公告" → `nte_notice`（本 skill，不是 everness）

# 规则

- 用户提到"异环 / yh / YH / nte / NTE / NTEUID / 环"且要查账号、面板、体力、签到、抽卡、攻略、配队、排行、登录绑定时，先 load_skill 本 skill。
- `<角色名/疑似角色名>面板` 必须调用 `nte_character(char_name)`，不要调用 `nte_box`。
- 角色名通过 NTEUID 注册的 `ai_alias`、角色知识库和语义相近关系规范化，不在 skill 内维护角色名单。
- `nte_box` 只用于"练度、box、全角色练度、练度统计、该练谁"。
- 图片工具会直接发送结果；调用前不要先发"发了、马上发"等文字，调用后不要补文字。
- 本 skill 没有 scripts；禁止调用 `run_skill_script(skill_name="nte-yihuan", ...)`。
