from gsuid_core.bot import Bot
from gsuid_core.models import Event

TITLE = "[异环]\n"


class CommonMsg:
    from ...nte_config.prefix import NTE_PREFIX

    NOT_LOGGED_IN = "尚未登录塔吉多账号"
    LOGIN_EXPIRED = f"登录已失效，请重新发送【{NTE_PREFIX}登录】"
    RETRY_LATER = "服务暂时不可用，请稍后再试"


class LoginMsg:
    from ...nte_config.prefix import NTE_PREFIX

    TIMEOUT = f"登录超时，请重新发送【{NTE_PREFIX}登录】"
    SESSION_EXPIRED = f"登录会话已失效，请重新发送【{NTE_PREFIX}登录】"
    SMS_LOGIN_FAILED = "验证码错误或已过期，请重新获取"
    USER_CENTER_LOGIN_FAILED = "登录失败，请稍后再试"
    NO_SUPPORTED_GAME = "登录失败，请绑定插件支持的游戏"
    SUCCESS = "登录成功"
    TAJIDUO_SUCCESS = "塔吉多登录成功"
    LINK_COPY = "请复制地址到浏览器打开"
    LINK_QR = "请扫描下方二维码获取登录地址，并复制地址到浏览器打开\n"
    LINK_TTL = "登录地址10分钟内有效"
    LINK_EXPIRED = f"链接已失效，请回到对话重新发送 {NTE_PREFIX}登录"
    MOBILE_INVALID = "手机号格式错误"
    CODE_INVALID = "验证码格式错误"
    SMS_SENT = "验证码已发送"
    SMS_SEND_FAILED = "验证码发送失败，请稍后再试"
    NOT_LOGGED_IN = "你还没有登录塔吉多账号"
    LOGOUT_DONE = "已退出登录，所有塔吉多账号已删除"
    REFRESH_NO_ACCOUNT = "你还没有登录塔吉多账号"


class SignMsg:
    from ...nte_config.prefix import NTE_PREFIX

    NOT_LOGGED_IN = f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{NTE_PREFIX}登录】"
    BATCH_BUSY = "已有批量签到任务在跑，请稍候再试"
    BATCH_SCHEDULE_BUSY = "已有批量签到任务在跑，本次定时跳过"
    NO_SIGN_ACCOUNT = "无可签账号"
    ACCOUNT_BUSY = "正在签到中，请稍候"
    FAILED = "签到失败，稍后再试"
    LOGIN_EXPIRED = CommonMsg.LOGIN_EXPIRED
    NO_ROLE = "未绑定角色，跳过游戏签到"
    AUTO_NO_ACCOUNT = CommonMsg.NOT_LOGGED_IN
    AUTO_ENABLED = "已开启自动签到"
    AUTO_DISABLED = "已关闭自动签到"


class SignRecordMsg:
    from ...nte_config.prefix import NTE_PREFIX

    NOT_LOGGED_IN = f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{NTE_PREFIX}登录】"
    LOGIN_EXPIRED = CommonMsg.LOGIN_EXPIRED
    LOAD_FAILED = "签到记录暂时无法获取，请稍后再试"
    EMPTY = "暂无签到奖励记录"


class RoleMsg:
    from ...nte_config.prefix import NTE_PREFIX

    NOT_LOGGED_IN = f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{NTE_PREFIX}登录】"
    LOGIN_EXPIRED = CommonMsg.LOGIN_EXPIRED
    LOAD_FAILED = "角色数据暂时无法获取，请稍后再试"
    LOCAL_EMPTY = "暂无本地角色详情数据"
    REFRESH_FAILED = "角色面板刷新失败，请稍后再试"
    REFRESH_DONE = "角色面板刷新完成"
    CHAR_NOT_FOUND = "未找到该角色（检查角色名）"
    USAGE_DETAIL = f"用法：{NTE_PREFIX}<角色名>面板，例如 {NTE_PREFIX}娜娜莉面板"
    EMPTY = "暂无可展示的数据"


class TeamMsg:
    from ...nte_config.prefix import NTE_PREFIX

    NOT_LOGGED_IN = f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{NTE_PREFIX}登录】"
    LOGIN_EXPIRED = CommonMsg.LOGIN_EXPIRED
    LOAD_FAILED = "配队推荐暂时无法获取，请稍后再试"
    EMPTY = "当前没有可用的配队推荐"
    NO_RECOMMENDATION = "当前没有该角色的配队推荐"
    CHAR_NOT_FOUND = "未找到该角色（检查角色名）"
    USAGE_DETAIL = f"用法：{NTE_PREFIX}<角色名>配队，例如 {NTE_PREFIX}娜娜莉配队"


class NoticeMsg:
    SUBSCRIBE_GROUP_ONLY = "请在群聊中订阅"
    UNSUBSCRIBE_GROUP_ONLY = "请在群聊中取消订阅"
    PUSH_CLOSED = "公告推送功能已关闭"
    ALREADY_SUBSCRIBED = "已经订阅了公告"
    SUBSCRIBED = "成功订阅公告"
    UNSUBSCRIBED = "成功取消订阅公告"
    NOT_SUBSCRIBED = "未曾订阅公告"
    EMPTY = "当前没有可用的公告内容"
    INVALID_POST_ID = "请输入正确的 postId"
    LOAD_FAILED = "公告暂时无法获取，请稍后再试"


async def send_nte_notify(bot: Bot, ev: Event, msg: str, need_at: bool = True):
    at_sender = need_at and bool(ev.group_id)
    return await bot.send(f"{TITLE}{msg}", at_sender=at_sender)
