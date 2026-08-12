from __future__ import annotations

import hashlib
import re
import time
import uuid
from base64 import b64encode
from dataclasses import dataclass
from typing import Any, ClassVar

import httpx

from gsuid_core.config import core_config
from gsuid_core.logger import logger

from ..nte_config.nte_config import NTEConfig
from ..utils.cache import TimedCache
from ..utils.database import NTEUser
from ..utils.utils import get_public_ip

SCRATCH_LOGIN_TTL = 600
SCRATCH_LOGIN_CACHE: TimedCache = TimedCache(timeout=SCRATCH_LOGIN_TTL, maxsize=64)

ID_BASE = "https://id.wanmei.com"
KF_PAGE = "https://kf.wanmei.com/selfItemFlowQuery?gameId=191"
LOGIN_PAGE_URL = f"{ID_BASE}/login"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "*/*",
    "X-Requested-With": "XMLHttpRequest",
}


class ScratchLoginError(RuntimeError):
    def __init__(self, message: str, raw: dict[str, Any] | None = None):
        super().__init__(message)
        self.message = message
        self.raw = raw or {}


@dataclass
class ScratchLoginState:
    user_id: str
    bot_id: str
    bot_self_id: str = ""
    user_type: str = "direct"
    group_id: str | None = None
    target_user_id: str = ""
    status: str = "pending"  # pending | success
    msg: str = ""
    client: "httpx.AsyncClient | None" = None
    roles: list[dict[str, Any]] | None = None  # 无塔吉多时待选的完美世界角色列表
    role_bound: bool = False  # 无塔吉多时是否已完成角色绑定


def scratch_auth_token(user_id: str) -> str:
    return hashlib.sha256(user_id.encode()).hexdigest()[:8]


def begin_scratch_login(
    user_id: str,
    bot_id: str,
    *,
    bot_self_id: str = "",
    user_type: str = "direct",
    group_id: str | None = None,
    target_user_id: str = "",
) -> str:
    auth = scratch_auth_token(user_id)
    close_scratch_client(auth)
    SCRATCH_LOGIN_CACHE.set(
        auth,
        ScratchLoginState(
            user_id=user_id,
            bot_id=bot_id,
            bot_self_id=bot_self_id,
            user_type=user_type,
            group_id=group_id,
            target_user_id=target_user_id or user_id,
        ),
    )
    return auth


async def scratch_login_page_url() -> str:
    url = NTEConfig.get_config("NTELoginUrl").data.strip()
    if url:
        return url if url.startswith("http") else f"https://{url}"
    host = core_config.get_config("HOST")
    port = core_config.get_config("PORT")
    if host in {"localhost", "127.0.0.1"}:
        host = "localhost"
    else:
        host = await get_public_ip(host)
    return f"http://{host}:{port}"


async def _post_form(
    client: httpx.AsyncClient,
    url: str,
    data: dict[str, Any],
    *,
    cookie: str = "",
) -> tuple[dict[str, Any], dict[str, str]]:
    """POST 表单，返回 (JSON, 响应 Set-Cookie 解析出的 Cookie 字典)。"""
    headers = dict(_HEADERS)
    if cookie:
        headers["Cookie"] = cookie
    resp = await client.post(url, data=data, headers=headers)
    cookies: dict[str, str] = {}
    for raw in resp.headers.get_list("set-cookie"):
        pair = raw.split(";", 1)[0]
        if "=" in pair:
            key, value = pair.split("=", 1)
            cookies[key.strip()] = value.strip()
    try:
        payload = resp.json()
    except Exception:
        payload = {"code": -1, "message": f"响应格式异常 HTTP {resp.status_code}"}
    if not isinstance(payload, dict):
        payload = {"code": -1, "message": "响应格式异常"}
    return payload, cookies


async def fetch_cap_ticket(auth: str) -> str:
    payload, _ = await _post_form(
        _client_for(auth),
        f"{ID_BASE}/user/security/getCapTicket",
        {"t": str(int(time.time() * 1000))},
    )
    if payload.get("code") != 0:
        raise ScratchLoginError(str(payload.get("message") or "获取验证码失败"), payload)
    result = str(payload.get("result") or "")
    if not result:
        raise ScratchLoginError("获取验证码失败：响应缺少 capTicket", payload)
    return result


async def fetch_kf_captcha(cookie: str) -> str:
    """从客服系统换取查询滑块验证码票据（appId 20003 配套），需要用户完整 Cookie。"""
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        resp = await client.get(
            "https://kf.wanmei.com/laohuService/getMCaptcha",
            headers={
                "User-Agent": USER_AGENT,
                "Cookie": cookie,
                "X-Requested-With": "XMLHttpRequest",
                "Referer": KF_PAGE,
            },
        )
    if resp.status_code in (301, 302, 303, 307, 308):
        raise ScratchLoginError(
            "刮刮乐 Cookie 已失效，请重新登录",
            {"status_code": resp.status_code, "location": resp.headers.get("location", "")},
        )
    text = resp.text.strip().strip('"')
    if not text or len(text) != 32:
        raise ScratchLoginError("获取查询验证码失败", {"text": resp.text[:200]})
    return text


def _client_for(auth: str) -> httpx.AsyncClient:
    """同一登录会话共用一个 httpx client（Cookie 持久化），否则验证码/登录会被判定为不同会话。"""
    state = SCRATCH_LOGIN_CACHE.get(auth)
    if state is None:
        raise ScratchLoginError("登录链接已失效，请重新发送【刮刮乐登录】")
    if state.client is None:
        state.client = httpx.AsyncClient(
            timeout=20,
            follow_redirects=False,
            trust_env=False,
        )
        SCRATCH_LOGIN_CACHE.set(auth, state)
    return state.client


def close_scratch_client(auth: str) -> None:
    state = SCRATCH_LOGIN_CACHE.get(auth)
    if state is not None and state.client is not None:
        client = state.client
        state.client = None
        SCRATCH_LOGIN_CACHE.set(auth, state)
        try:
            import asyncio

            asyncio.get_running_loop().create_task(client.aclose())
        except Exception:
            pass


async def _fetch_login_page(client: httpx.AsyncClient) -> tuple[str, str, str]:
    """抓登录页取当前 RSA 公钥 / jsessionId / capTicket。"""
    resp = await client.get(LOGIN_PAGE_URL, headers=_HEADERS)
    html = resp.text
    match_pk = re.search(r'id="publicKey"[^>]*value="([^"]+)"', html)
    match_js = re.search(r'id="jsessionId"[^>]*value="([^"]+)"', html)
    match_ct = re.search(r"capTicket\s*=\s*'([^']+)'", html)
    if not match_pk or not match_js:
        raise ScratchLoginError("获取登录页参数失败")
    return match_pk.group(1), match_js.group(1), (match_ct.group(1) if match_ct else "")


def _rsa_oaep_encrypt(public_key_pem: str, value: str) -> str:
    from Crypto.Cipher import PKCS1_OAEP
    from Crypto.Hash import SHA1
    from Crypto.PublicKey import RSA

    key = RSA.import_key(public_key_pem)
    cipher = PKCS1_OAEP.new(key, hashAlgo=SHA1)
    return b64encode(cipher.encrypt(value.encode("utf-8"))).decode()


async def send_scratch_sms(auth: str, phone: str, cap_ticket: str, sec_code: str) -> None:
    payload, _ = await _post_form(
        _client_for(auth),
        f"{ID_BASE}/sendPhoneCaptchaForSlidCaptcha",
        {
            "nationAreaId": "1",
            "phone": phone,
            "capTicket": cap_ticket,
            "secCode": sec_code,
        },
    )
    if payload.get("code") != 0:
        raise ScratchLoginError(str(payload.get("message") or "短信发送失败"), payload)


async def finish_scratch_login(
    auth: str,
    user_id: str,
    bot_id: str,
    phone: str,
    code: str,
    cap_ticket: str,
    sec_code: str,
) -> tuple[str, list[dict[str, Any]]]:
    """完成短信登录并落库，返回 (拼接好的 kf.wanmei.com Cookie, 待选角色列表)。

    已登录塔吉多的用户直接复用其角色行（roles 为空）；没有塔吉多登录时拉取
    完美世界角色列表，由业务层自动绑定唯一角色或引导用户选择。
    """
    client = _client_for(auth)
    public_key, jsession_id, _page_cap = await _fetch_login_page(client)
    fake_device = f"PC-{uuid.uuid4().hex[:16].upper()}"
    await _post_form(
        client,
        f"{ID_BASE}/setDeviceInfo",
        {
            "jsessionId": jsession_id,
            "deviceId": fake_device,
            "deviceModel": "Chrome",
            "deviceSys": "Windows",
        },
    )

    check, _ = await _post_form(
        client,
        f"{ID_BASE}/checkPhoneCaptcha",
        {"phone": phone, "phoneCaptcha": code},
    )
    if check.get("code") != 0:
        message = str(check.get("message") or "手机验证码输入错误")
        logger.warning(f"[刮刮乐] checkPhoneCaptcha 失败 {phone}: {check}")
        raise ScratchLoginError(message, check)

    location = f"{await scratch_login_page_url()}/nte/scratch/{scratch_auth_token(user_id)}"
    payload, cookies = await _post_form(
        client,
        f"{ID_BASE}/shortMessageLogon",
        {
            "phoneNumber": _rsa_oaep_encrypt(public_key, phone),
            "newCaptcha": _rsa_oaep_encrypt(public_key, code),
            "nationAreaId": "1",
            "capTicket": cap_ticket,
            "secCode": sec_code,
            "location": location,
            "state": jsession_id,
        },
    )
    if payload.get("code") != 0:
        raise ScratchLoginError(str(payload.get("message") or "登录失败"), payload)

    logger.warning(f"[刮刮乐] shortMessageLogon 成功 payload_keys={list(payload)} cookie_keys={list(cookies)}")
    wm_logon = cookies.get("wmLogon") or ""
    captured = "direct"
    if not wm_logon:
        # 部分情况下 wmLogon 在回跳链路里下发：跟随 result/location 收全 Cookie
        follow_url = ""
        for key in ("result", "location", "url"):
            candidate = payload.get(key)
            if isinstance(candidate, str) and candidate.startswith("http"):
                follow_url = candidate
                break
        if follow_url:
            resp = await client.get(
                follow_url,
                headers={"User-Agent": USER_AGENT, "Referer": LOGIN_PAGE_URL},
            )
            for raw in resp.headers.get_list("set-cookie"):
                pair = raw.split(";", 1)[0]
                if "=" in pair and pair.split("=", 1)[0].strip().lower() == "wmlogon":
                    wm_logon = pair.split("=", 1)[1].strip()
                    captured = "follow"
                    break
    if not wm_logon:
        raise ScratchLoginError("登录响应缺少 wmLogon Cookie", {"cookies": cookies, "payload": payload})
    logger.warning(
        f"[刮刮乐] 捕获 wmLogon captured={captured} len={len(wm_logon)} "
        f"prefix={wm_logon[:24]}… cookie_keys={list(cookies)}"
    )

    # 客服端可能校验 logon / wmLogon 等组合，整串 Cookie 一起存
    # 只保留可安全放进 Cookie 头的键值（值里不能有 ; 或空白）
    safe_pairs = [
        f"{key}={value}"
        for key, value in cookies.items()
        if value and ";" not in value and not any(ch.isspace() for ch in value)
    ]
    full_cookie = "; ".join(safe_pairs)
    # 客服页 SESSION 换取仅作增强：换取失败不阻塞登录
    try:
        cookie = await _kf_session_cookie(full_cookie)
    except ScratchLoginError as error:
        logger.warning(f"[刮刮乐] kf SESSION 换取失败（降级为全量 Cookie）: {error.message}")
        cookie = full_cookie
    await NTEUser.bind_wm_cookie(user_id, bot_id, cookie)
    logger.info(f"[刮刮乐] user_id={user_id} 网页登录绑定成功")
    tajiduo = await NTEUser.get_active(user_id, bot_id)
    if tajiduo is not None:
        return cookie, []
    roles = await fetch_wanmei_roles(cookie)
    if not roles:
        raise ScratchLoginError("未获取到完美世界角色列表，请重试或联系管理员")
    return cookie, roles


async def _kf_session_cookie(cookie: str) -> str:
    """用已有 Cookie 访问客服页换取 kf.wanmei.com 的 SESSION，返回完整 Cookie。"""
    variants = [cookie]
    decoded = cookie.replace("%7C", "|").replace("%3D", "=").replace("%2F", "/").replace("%2B", "+")
    if decoded != cookie:
        variants.append(decoded)
    async with httpx.AsyncClient(
        timeout=20,
        follow_redirects=False,
        trust_env=False,
    ) as client:
        resp = None
        for variant in variants:
            resp = await client.get(
                KF_PAGE,
                headers={"User-Agent": USER_AGENT, "Cookie": variant},
            )
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
    assert resp is not None
    if resp.status_code in (301, 302, 303, 307, 308):
        location = resp.headers.get("location", "")
        logger.warning(f"[刮刮乐] kf 拒绝 wmLogon: HTTP {resp.status_code} → {location[:120]}")
        raise ScratchLoginError(
            "wmLogon 已失效，请重新登录",
            {"status_code": resp.status_code, "location": location},
        )
    parts = [pair for pair in variant.split(";") if pair.strip()]
    for raw in resp.headers.get_list("set-cookie"):
        pair = raw.split(";", 1)[0]
        if "=" in pair and pair.split("=", 1)[0].strip().upper() == "SESSION":
            if not any(p.split("=", 1)[0].strip().upper() == "SESSION" for p in parts):
                parts.append(pair)
    return "; ".join(parts)


async def fetch_wanmei_roles(cookie: str) -> list[dict[str, Any]]:
    """用已登录 Cookie 拉取完美世界客服系统的角色列表（gameId=191 异环）。"""
    variants = [cookie]
    decoded = cookie.replace("%7C", "|").replace("%3D", "=").replace("%2F", "/").replace("%2B", "+")
    if decoded != cookie:
        variants.append(decoded)
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        resp = None
        for variant in variants:
            resp = await client.get(
                "https://kf.wanmei.com/laohuSelfService/searchActiveGameRoles?gameId=191",
                headers={"User-Agent": USER_AGENT, "Cookie": variant},
            )
            if resp.status_code not in (301, 302, 303, 307, 308):
                break
    assert resp is not None
    if resp.status_code in (301, 302, 303, 307, 308):
        raise ScratchLoginError(
            "wmLogon 已失效，请重新登录",
            {"status_code": resp.status_code, "location": resp.headers.get("location", "")[:120]},
        )
    try:
        payload = resp.json()
    except ValueError as err:
        raise ScratchLoginError("角色列表响应异常", {"text": resp.text[:200]}) from err
    if not isinstance(payload, list):
        return []
    roles = []
    for item in payload:
        role_id = str(item.get("roleId") or "")
        role_name = str(item.get("roleName") or "")
        if role_id and role_name:
            roles.append({"roleId": role_id, "roleName": role_name})
    return roles
