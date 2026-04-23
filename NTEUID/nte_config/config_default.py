from typing import Dict

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsListConfig,
    GsTimeRConfig,
    GsListStrConfig,
)

from ..utils.constants import (
    TASK_KEY_SHARE,
    TASK_KEY_LIKE_POST,
    TASK_KEY_BROWSE_POST,
)

CONFIG_DEFAULT: Dict[str, GSC] = {
    "NTEAnnIds": GsListConfig(
        "推送公告ID",
        "异环公告推送ID列表",
        [],
    ),
    "NTEAnnOpen": GsBoolConfig(
        "公告推送总开关",
        "异环公告推送总开关",
        True,
    ),
    "NTEAnnCheckMinutes": GsIntConfig(
        "公告检测时间（单位min）",
        "公告检测时间（单位min）",
        10,
        60,
    ),
    "NTELoginUrl": GsStrConfig(
        "异环登录页面URL",
        "登录页对外域名；留空则用 Core 的 HOST/PORT 并自动探测公网 IP",
        "",
    ),
    "NTETencentWord": GsBoolConfig(
        "登录链接用腾讯文档包装",
        "开启后把登录链接外套一层 docs.qq.com 跳转，避免平台屏蔽",
        False,
    ),
    "NTEQRLogin": GsBoolConfig(
        "登录链接变二维码",
        "开启后登录链接转成二维码图片发送",
        False,
    ),
    "NTELoginForward": GsBoolConfig(
        "登录链接用转发消息发送",
        "开启后把登录消息包在合并转发里，避免链接风控",
        False,
    ),
    "NTESignDaily": GsBoolConfig(
        "开启每日签到",
        "关闭后将不再执行定时签到任务",
        True,
    ),
    "NTESignTime": GsTimeRConfig(
        "定时签到时间",
        "每天自动签到时间（时, 分），重启后生效",
        (0, 30),
    ),
    "NTESignAll": GsBoolConfig(
        "定时签全员",
        "开启后定时任务签所有已登录账号；关闭则只签发送过【开启自动签到】的账号",
        False,
    ),
    "NTESignConcurrency": GsIntConfig(
        "自动签到并发",
        "同时跑的账号数，最大 30",
        5,
        max_value=30,
    ),
    "NTESignMaster": GsBoolConfig(
        "签到结果推送给主人",
        "开启后会把每日签到汇总推送给主人",
        False,
    ),
    "NTETaskDaily": GsBoolConfig(
        "开启社区任务",
        "签到时附带执行浏览/点赞等每日金币任务",
        True,
    ),
    "NTETaskKinds": GsListStrConfig(
        "参与的社区任务",
        "勾选哪些每日金币任务自动做",
        [TASK_KEY_BROWSE_POST, TASK_KEY_LIKE_POST, TASK_KEY_SHARE],
        options=[TASK_KEY_BROWSE_POST, TASK_KEY_LIKE_POST, TASK_KEY_SHARE],
    ),
    "NTETaskMaxFailures": GsIntConfig(
        "社区任务连续失败上限",
        "单个子任务连续失败到此次数就停止本轮",
        3,
        max_value=10,
    ),
    "NTETaskActionDelay": GsListConfig(
        "社区任务动作间隔（秒）",
        "每次浏览/点赞/分享之间随机 sleep 的 [min, max]",
        [1, 3],
    ),
    "NTESignBatchDelay": GsTimeRConfig(
        "批次签到间隔（秒）",
        "自动签到多账号分批之间的 sleep 窗口 (min, max)",
        (0, 2),
    ),
    "NTEProxyUrl": GsStrConfig(
        "代理地址",
        "SDK 请求走的代理（http://host:port），为空则直连",
        "",
    ),
}
