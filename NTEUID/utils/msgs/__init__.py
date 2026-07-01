from gsuid_core.bot import Bot
from gsuid_core.models import Event

from ..constants import TAPTAP_BIND_GUIDE_URL
from ...nte_config.prefix import nte_prefix
from ...nte_config.nte_config import NTEConfig

TITLE = "[异环]\n"


class CommonMsg:
    NOT_LOGGED_IN = "尚未登录塔吉多账号"
    RETRY_LATER = "服务暂时不可用，请稍后再试"
    AT_QUERY_DISABLED = "AT 查询功能未开启，无法查看他人信息"

    @classmethod
    def login_expired(cls) -> str:
        p = nte_prefix()
        return f"登录已失效，请先发送【{p}刷新令牌】尝试续签，失败后再【{p}登录】"

    @classmethod
    def not_logged_in(cls, *, has_history: bool = False) -> str:
        if has_history:
            return cls.login_expired()
        return f"{cls.NOT_LOGGED_IN}，请先发送【{nte_prefix()}登录】"


class LoginMsg:
    SMS_LOGIN_FAILED = "验证码错误或已过期，请重新获取"
    USER_CENTER_LOGIN_FAILED = "登录失败，请稍后再试"
    NO_SUPPORTED_GAME = "登录失败，请绑定插件支持的游戏"
    SUCCESS = "登录成功"
    TAJIDUO_SUCCESS = "塔吉多登录成功"
    ACCESS_TOKEN_SHELL_SUCCESS = "登录成功，角色信息暂未同步"
    LINK_COPY = "请复制地址到浏览器打开"
    LINK_QR = "请扫描下方二维码获取登录地址，并复制地址到浏览器打开\n"
    MOBILE_INVALID = "手机号格式错误"
    CODE_INVALID = "验证码格式错误"
    SMS_SENT = "验证码已发送"
    SMS_SEND_FAILED = "验证码发送失败，请稍后再试"
    SMS_VERIFIED = "短信验证通过，请回到对话查看登录结果"
    NOT_LOGGED_IN = "你还没有登录塔吉多账号"
    LOGOUT_DONE = "已退出登录，当前塔吉多账号已删除"
    LOGOUT_ALL_DONE = "已退出登录，所有塔吉多账号已删除"
    REFRESH_NO_ACCOUNT = "你还没有登录塔吉多账号"

    @classmethod
    def link_ttl(cls) -> str:
        ttl_s = NTEConfig.get_config("NTELoginTTL").data
        if ttl_s >= 60 and ttl_s % 60 == 0:
            return f"登录地址{ttl_s // 60}分钟内有效"
        return f"登录地址{ttl_s}秒内有效"

    @classmethod
    def timeout(cls) -> str:
        return f"登录超时，请重新发送【{nte_prefix()}登录】"

    @classmethod
    def session_expired(cls) -> str:
        return f"登录会话已失效，请重新发送【{nte_prefix()}登录】"

    @classmethod
    def link_expired(cls) -> str:
        return f"链接已失效，请回到对话重新发送 {nte_prefix()}登录"


class SignMsg:
    BATCH_BUSY = "已有批量签到任务在跑，请稍候再试"
    BATCH_SCHEDULE_BUSY = "已有批量签到任务在跑，本次定时跳过"
    NO_SIGN_ACCOUNT = "无可签账号"
    ACCOUNT_BUSY = "正在签到中，请稍候"
    FAILED = "签到失败，稍后再试"
    AUTO_NO_ACCOUNT = CommonMsg.NOT_LOGGED_IN
    AUTO_ENABLED = "已开启自动签到"
    AUTO_DISABLED = "已关闭自动签到"
    AUTO_DAILY_DISABLED = "定时签到功能已关闭"
    CALENDAR_LOAD_FAILED = "签到日历加载失败，请稍后再试"
    CALENDAR_EMPTY = "暂无签到奖励数据"

    @classmethod
    def login_expired(cls) -> str:
        return CommonMsg.login_expired()


class RoleMsg:
    """玩家存档（roleId 维度）相关文案：主页加载、刷新、登录态等。"""

    LOAD_FAILED = "角色数据暂时无法获取，请稍后再试"
    REFRESH_FAILED = "角色面板刷新失败，请稍后再试"
    EMPTY = "暂无可展示的数据"

    @classmethod
    def not_logged_in(cls, is_other: bool = False, *, has_history: bool = False) -> str:
        if is_other:
            return "对方登录已失效，无法查询" if has_history else "对方尚未登录塔吉多账号"
        if has_history:
            return CommonMsg.login_expired()
        return f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{nte_prefix()}登录】"

    @classmethod
    def login_expired(cls, is_other: bool = False) -> str:
        if is_other:
            return "对方登录已失效，无法查询"
        return CommonMsg.login_expired()


class CharacterMsg:
    """可玩角色（charId 维度）相关文案：详情查询、本地缓存。"""

    NOT_FOUND = "未找到该角色（检查角色名）"
    LOCAL_EMPTY = "暂无本地角色详情数据"
    OTHER_LOCAL_EMPTY = "对方暂无本地角色详情数据"

    @classmethod
    def usage_detail(cls) -> str:
        p = nte_prefix()
        return f"用法：{p}<角色名>面板，例如 {p}娜娜莉面板"


class RankMsg:
    """角色评分群排名相关文案。"""

    GROUP_ONLY = "评分排名只能在群里使用"
    NO_MEMBER = "本群还没有人刷新过面板，无法排名"
    NO_SCORE = "暂无该角色的可评分数据（需先刷新面板）"

    @classmethod
    def usage(cls) -> str:
        p = nte_prefix()
        return f"用法：{p}<角色名>排名，例如 {p}娜娜莉排名"

    @classmethod
    def usage_bot(cls) -> str:
        p = nte_prefix()
        return f"用法：{p}<角色名>bot排名，例如 {p}娜娜莉bot排名"


class TeamMsg:
    LOAD_FAILED = "配队推荐暂时无法获取，请稍后再试"
    EMPTY = "当前没有可用的配队推荐"
    NO_RECOMMENDATION = "当前没有该角色的配队推荐"
    CHAR_NOT_FOUND = "未找到该角色（检查角色名）"

    @classmethod
    def usage_detail(cls) -> str:
        p = nte_prefix()
        return f"用法：{p}<角色名>配队，例如 {p}娜娜莉配队"


class BindMsg:
    ONLY_ONE_ACCOUNT = "当前仅绑定了 1 个塔吉多账号，无需切换"
    TOKEN_EMPTY = "未找到可用的塔吉多凭证"

    @classmethod
    def switch_done(cls, center_uid: str, role_name: str, uid: str) -> str:
        role = f"\n当前角色：{role_name}（{uid}）" if role_name and uid else ""
        return f"已切换到塔吉多账号 {center_uid}{role}"

    @classmethod
    def target_not_found(cls) -> str:
        return f"未在已绑定账号中找到目标，可先发送【{nte_prefix()}查看】确认"


class GuideMsg:
    CHAR_NOT_FOUND = "未找到角色【{char_name}】，请检查名称"
    EMPTY = "角色【{char_name}】暂无攻略图"


class CatalogMsg:
    NOT_FOUND = "未找到【{name}】对应的角色或武器，请检查名称"
    EMPTY = "【{name}】暂无图鉴"
    LIST_EMPTY = "暂无名册资源，请先发送【下载全部资源】"


class AliasMsg:
    EMPTY_NAME_OR_ALIAS = "名称或别名不能为空"
    INVALID_ACTION = "无效的操作，请检查操作"
    NOT_FOUND = "【{name}】不存在于角色或武器中，请检查名称"
    ALIAS_IN_USE = "别名【{alias}】已被{kind}【{name}】占用"
    ALIAS_NOT_REMOVABLE = "别名【{alias}】不存在或为预置别名，无法删除"
    ADD_SUCCESS = "成功为{kind}【{name}】添加别名【{alias}】"
    DEL_SUCCESS = "成功为{kind}【{name}】删除别名【{alias}】"

    @classmethod
    def usage_list(cls) -> str:
        p = nte_prefix()
        return f"用法：{p}<角色名/武器名>别名 或 {p}<角色名/武器名>别名列表，例如 {p}娜娜莉别名"


class StaminaMsg:
    PUSH_CLOSED = "体力推送总开关已关闭"
    NOT_SUBSCRIBED = "未订阅体力推送，无需取消"
    UNSUBSCRIBED_ALL = "已取消全部体力推送"
    NO_SUBSCRIBERS = "当前没有体力订阅"

    @classmethod
    def threshold_invalid(cls, lo: int, hi: int) -> str:
        return f"阈值需要是 {lo}-{hi} 范围内的整数"

    @classmethod
    def subscribed(cls, role_name: str, threshold: int) -> str:
        return f"已开启【{role_name}】体力推送，阈值 {threshold}"

    @classmethod
    def threshold_updated(cls, role_name: str, threshold: int) -> str:
        return f"已更新【{role_name}】体力推送阈值为 {threshold}"

    @classmethod
    def unsubscribed(cls, role_name: str) -> str:
        return f"已取消【{role_name}】体力推送"

    @classmethod
    def all_deleted(cls, count: int) -> str:
        return f"已删除所有体力订阅，共 {count} 条"

    @classmethod
    def stamina_reached(cls, role_name: str, value: int, maximum: int) -> str:
        return f"{role_name} 本性像素已达到 {value}/{maximum}，记得去消耗哦～"


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


class GachaMsg:
    INVALID_TAP_ID = "TapTap user_id 必须是数字"
    INVALID_QUERY = "抽卡记录参数必须是 TapTap user_id 或小黑盒 user_pkey"
    TAPTAP_NOT_BOUND = f"该 TapTap 账号未绑定异环角色，\n请先完成绑定：{TAPTAP_BIND_GUIDE_URL}"
    LOAD_FAILED = "抽卡数据获取失败，请稍后再试"
    XHH_TARGET_NOT_BOUND = "该小黑盒账号未绑定异环角色"
    XHH_PKEY_EXPIRED = "小黑盒凭据已失效，请重新获取"

    @classmethod
    def not_logged_in(cls, is_other: bool = False, *, has_history: bool = False) -> str:
        if is_other:
            return "对方登录已失效，无法查询" if has_history else "对方尚未登录塔吉多账号"
        if has_history:
            return CommonMsg.login_expired()
        return f"{CommonMsg.NOT_LOGGED_IN}，请先发送【{nte_prefix()}登录】"

    @classmethod
    def login_expired(cls, is_other: bool = False) -> str:
        if is_other:
            return "对方登录已失效，无法查询"
        return CommonMsg.login_expired()

    @classmethod
    def empty(cls, role_name: str) -> str:
        return f"【{role_name}】暂无抽卡数据，\n请去数据源刷新后再试"


async def send_nte_notify(
    bot: Bot,
    ev: Event,
    msg: str,
    need_at: bool = True,
) -> None:
    at_sender = need_at and bool(ev.group_id)
    await bot.send(f"{TITLE}{msg}", at_sender=at_sender)
