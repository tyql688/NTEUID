from __future__ import annotations

from gsuid_core.utils.plugins_config.models import (
    GSC,
    GsIntConfig,
    GsStrConfig,
    GsBoolConfig,
    GsListConfig,
    GsTimeConfig,
    GsListStrConfig,
)

from ..utils.constants import (
    TASK_KEY_SHARE,
    TASK_KEY_LIKE_POST,
    TASK_KEY_BROWSE_POST,
)

try:
    from gsuid_core.utils.plugins_config.models import GsTimeRConfig

    _sign_time_config: GSC = GsTimeRConfig(
        "定时签到时间",
        "每天自动签到时间（时, 分），重启后生效",
        (0, 30),
    )
except ImportError:
    _sign_time_config = GsTimeConfig(
        "定时签到时间",
        "每天自动签到时间（HH:MM），重启后生效",
        "00:30",
    )

CONFIG_DEFAULT: dict[str, GSC] = {
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
        "公告检测时间（单位min），重启后生效",
        10,
        60,
    ),
    "NTELoginUrl": GsStrConfig(
        "异环登录页面URL",
        "local 模式：登录页对外域名，留空则用 Core 的 HOST/PORT 并自动探测公网 IP；外置模式：必填 nte-login 服务的 base URL",
        "",
    ),
    "NTELoginTransport": GsStrConfig(
        "登录接入方式",
        "local = Core 进程内嵌登录；http_poll / sse / ws = 走外置 nte-login 服务",
        "local",
        options=["local", "http_poll", "sse", "ws"],
    ),
    "NTELoginSecret": GsStrConfig(
        "外置登录共享密钥",
        "外置模式下与 nte-login 服务的 SHARED_SECRET 一致；HMAC 校验，留空则不签名",
        "",
    ),
    "NTELoginTTL": GsIntConfig(
        "登录会话存活秒数",
        "用户收到链接后多久内必须完成登录；超时后通知「登录超时」并清理。最大 3600",
        600,
        max_value=3600,
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
    "NTESignHuanta": GsBoolConfig(
        "签到时一并签幻塔",
        "打开后同账号下的幻塔角色也会一起签；老账号首次打开后需要执行一次【刷新令牌】补拉幻塔角色",
        False,
    ),
    "NTESignTime": _sign_time_config,
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
    "NTESignPushPrivate": GsBoolConfig(
        "签到结果推送私聊",
        "私聊开启自动签到的用户，定时签到完成后推送给本人私聊",
        False,
    ),
    "NTESignPushGroup": GsBoolConfig(
        "签到结果推送群聊",
        "群里开启自动签到的用户，定时签到完成后按群聚合推送回该群",
        False,
    ),
    "NTESignPushPic": GsBoolConfig(
        "签到推送带标题图",
        "群推送时使用汇总标题图；关闭则发简要文字",
        True,
    ),
    "NTETaskDaily": GsBoolConfig(
        "开启社区任务",
        "签到时附带执行浏览/点赞等每日金币任务",
        True,
    ),
    "NTETaskKinds": GsListStrConfig(
        "参与的社区任务",
        "勾选哪些每日金币任务自动做",
        data=[TASK_KEY_BROWSE_POST, TASK_KEY_LIKE_POST, TASK_KEY_SHARE],
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
    "NTESignBatchDelay": GsListConfig(
        "批次签到间隔（秒）",
        "自动签到多账号分批之间的 sleep 窗口 [min, max]",
        [0, 2],
    ),
    "NTEGuide": GsListStrConfig(
        "角色攻略图提供方",
        "使用 nte 角色攻略时选择的提供方",
        data=["all"],
        options=["all", "零号攻略组"],
    ),
    "NTEProxyUrl": GsStrConfig(
        "代理地址",
        "SDK 请求走的代理（http://host:port），为空则直连",
        "",
    ),
    "NTEAllowAtQuery": GsBoolConfig(
        "允许AT查询他人信息",
        "开启后可通过 @他人 查询对方的角色面板等信息；关闭则统一只查自己",
        True,
    ),
}
