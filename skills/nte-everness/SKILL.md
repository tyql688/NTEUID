---
name: nte-everness
description: 异环 yh YH nte NTE NTEUID 环 — 用户要查公开资料、活动日历、角色详情技能背景生日CV、异能环合元素反应、驱动块模块core套装、弧盘效果材料、道具来源、模糊搜索游戏资料时，先 load_skill 阅读本说明。不需要用户登录。说明型 skill，不含 scripts。
version: 0.1.0
plugin: NTEUID
source: https://everness.info/zh-Hans
---

# AI 工具

这些名字是 `ai_tools`，不是 skill script；不要用 `run_skill_script` 调用它们。

- 活动日历：调用 AI 工具 `everness_activity`
  触发：活动 / 活动日历 / 当前活动 / 活动时间表 / 活动什么时候结束 / 近期活动
- 角色资料：调用 AI 工具 `everness_character`，参数 name
  触发：角色详情 / 角色背景 / 技能描述 / 觉醒 / 共鸣 / 生日 / 阵营 / CV / 基础属性 / 角色介绍
- 异能环合：调用 AI 工具 `everness_esper_cycle`，参数 name（可留空）
  触发：异能环合 / 元素组合 / 元素反应 / 延滞 / 创生 / 覆纹 / 黯星 / 浊燃 / 浸染
- 驱动块：调用 AI 工具 `everness_drive_block`，参数 name
  触发：驱动块 / 模块 / Module / core / 主属性 / 副属性 / 格数 / 套装效果 / 圣遗物
- 弧盘：调用 AI 工具 `everness_arc`，参数 name
  触发：弧盘 / 弧盘效果 / 弧盘属性 / 弧盘材料 / 弧盘来源
- 资料搜索：调用 AI 工具 `everness_search`，参数 keyword、category（可选）、limit（可选）
  触发：搜一下 / 查一下 / 不知道叫什么 / 模糊搜索

# 分类

- 角色资料：背景、生日、阵营、CV、技能、觉醒、共鸣。
- 异能环合：元素组合、环合效果、延滞、创生、覆纹、黯星、浊燃、浸染。
- 驱动块：模块、core、Type II/III/IV Module、主属性、副属性、格数、套装效果。
- 弧盘：弧盘效果、弧盘属性、弧盘材料。
- 资料搜索：道具、材料、来源、活动、角色、弧盘、驱动块、异能环合。

# 与 nte-yihuan 的边界（硬性）

- **本 skill 负责**：公开资料查询 — 不需要用户登录账号。
- **nte-yihuan 负责**：用户账号数据（面板、练度、评分、体力、抽卡记录、签到）、攻略图、配队推荐、登录绑定。
- 互斥规则：
  - "技能描述 / 背景 / 生日 / CV / 基础属性" → `everness_character`（本 skill）
  - "攻略 / 配装 / 养成推荐" → 不在本 skill，引导到 `nte-yihuan` 的 `nte_guide`
  - "公告 / 最新公告" → 不在本 skill，引导到 `nte-yihuan` 的 `nte_notice`

# 规则

- 用户提到"异环 / yh / YH / nte / NTE / NTEUID / 环"且要查公开资料、活动、角色背景、异能环合、驱动块、弧盘、道具来源时，先 load_skill 本 skill。
- Everness 查询默认使用 `zh-Hans` 中文数据。
- 不需要用户账号；用户面板、练度、评分、体力、抽卡记录、签到用 `nte-yihuan`。
- 活动日历按 `generated_at`、`ongoing`、`upcoming`、`ended_recent` 回答；`ended_older` 只说明数量，不展开。
- 不知道具体异能环合名称时，`everness_esper_cycle` 的 `name` 留空。
- 不知道准确名称时，先用 `everness_search` 模糊搜索，再根据结果调用对应详情工具。
- 本 skill 没有 scripts；禁止调用 `run_skill_script(skill_name="nte-everness", ...)`。
