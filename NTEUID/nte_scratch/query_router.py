from __future__ import annotations

import json
import time
from pathlib import Path
from urllib.parse import quote

import httpx
from fastapi import Request, Response
from pydantic import BaseModel
from fastapi.staticfiles import StaticFiles
from starlette.responses import HTMLResponse, JSONResponse

from gsuid_core.bot import Bot
from gsuid_core.gss import gss
from gsuid_core.logger import logger
from gsuid_core.models import Event
from gsuid_core.web_app import app

from ..utils.msgs import ScratchMsg
from .scratch_login import SCRATCH_LOGIN_CACHE, ScratchLoginError, fetch_kf_captcha
from ..utils.database import NTEUser
from .scratch_service import _record_query_done, build_scratch_report
from ..utils.resource.RESOURCE_PATH import NTE_TEMPLATES

# 验证码组件本地化：手机端无法访问完美世界 CDN 时也能加载滑块
# 静态资产随功能代码放在 nte_scratch/static/nte_captcha（不走 resource/ 资源仓库）
_CAPTCHA_STATIC_DIR = Path(__file__).resolve().parent / "static" / "nte_captcha"
try:
    # 目录不存在时静默跳过挂载，避免影响 NTEUI 其他功能
    _CAPTCHA_STATIC_DIR.mkdir(parents=True, exist_ok=True)
    app.mount(
        "/nte/static/captcha",
        StaticFiles(directory=_CAPTCHA_STATIC_DIR),
        name="nte_captcha",
    )
except Exception:
    logger.warning("[刮刮乐] 验证码静态资源目录不可用，跳过挂载 /nte/static/captcha")

_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate"}
_CAPTCHA_API = "https://captchas.wanmei.com"
_PROXY_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def _json(ok: bool, msg: str = "", **extra: object) -> JSONResponse:
    return JSONResponse({"ok": ok, "msg": msg, **extra})


def _state(auth: str):
    state = SCRATCH_LOGIN_CACHE.get(auth)
    if state is None:
        return None, _json(False, "链接已失效，请回到 QQ 重新发送【刮刮乐】")
    return state, None


class _CapPayload(BaseModel):
    auth: str


class _QueryPayload(BaseModel):
    auth: str
    capTicket: str
    secCode: str
    days: int = 60


class _CapKeyPayload(BaseModel):
    auth: str
    appId: str
    capTicket: str


class _CapInfoPayload(BaseModel):
    auth: str
    capKey: str


class _CapValidatePayload(BaseModel):
    auth: str
    capKey: str | int | None = None
    validData: str | int | None = None
    op: str | int | None = None
    fp: str | int | None = None
    label: object = 0
    appId: str | None = None
    capTicket: str | int | None = None


async def _send_qq(state, image: bytes) -> bool:
    ev = Event(
        bot_id=state.bot_id,
        user_id=state.user_id,
        bot_self_id=state.bot_self_id,
        user_type=state.user_type,
        group_id=state.group_id,
        real_bot_id=state.bot_id,
        msg_id="",
    )
    if not gss.active_bot:
        logger.warning("[刮刮乐] 发送战报失败：无活跃 Bot（active_bot 为空）")
        return False
    bot = None
    if state.bot_id in gss.active_bot:
        bot = gss.active_bot[state.bot_id]
    else:
        for candidate in gss.active_bot.values():
            if getattr(candidate, "bot_id", None) == state.bot_id:
                bot = candidate
                break
    if bot is None:
        # 兼容不同版本的 active_bot 键名：单机器人环境直接回退到首个活跃连接
        logger.debug(f"[刮刮乐] 未按 bot_id={state.bot_id} 匹配，回退首个活跃 Bot: keys={list(gss.active_bot)[:5]}")
        bot = next(iter(gss.active_bot.values()))
    try:
        await Bot(bot, ev).send(image)
        return True
    except Exception as err:  # noqa: BLE001
        logger.warning(f"[刮刮乐] 发送战报失败: {err!r}")
        return False


@app.get("/nte/scratch/query/{auth_token}")
async def scratch_query_page(auth_token: str) -> HTMLResponse:
    state = SCRATCH_LOGIN_CACHE.get(auth_token)
    if state is None:
        return HTMLResponse("链接已失效，请回到 QQ 重新发送【刮刮乐】", status_code=404, headers=_NO_CACHE)
    return HTMLResponse(
        NTE_TEMPLATES.get_template("scratch_query.html").render(
            auth=auth_token,
            version=str(int(time.time())),
        ),
        headers=_NO_CACHE,
    )


@app.post("/nte/scratch/queryCapTicket")
async def scratch_query_cap(payload: _CapPayload) -> JSONResponse:
    state = SCRATCH_LOGIN_CACHE.get(payload.auth)
    if state is None:
        return _json(False, "链接已失效，请重新发送【刮刮乐】")
    target_user_id = state.target_user_id or state.user_id
    user = await NTEUser.get_scratch_user(target_user_id, state.bot_id)
    if user is None:
        return _json(False, "尚未绑定刮刮乐账号，请先发送【刮刮乐】完成登录")
    if not user.wm_cookie:
        return _json(False, "尚未绑定刮刮乐 Cookie，请先发送【刮刮乐登录】")
    try:
        cap_ticket = await fetch_kf_captcha(user.wm_cookie)
    except ScratchLoginError as error:
        logger.warning(f"[刮刮乐] 查询验证码获取失败: {error.message}")
        return _json(False, error.message)
    return _json(True, "", capTicket=cap_ticket, capAppId="20003")


@app.post("/nte/scratch/doQuery")
async def scratch_do_query(payload: _QueryPayload) -> JSONResponse:
    state, err = _state(payload.auth)
    if err is not None:
        return err
    days = max(1, min(60, payload.days))
    target_user_id = state.target_user_id or state.user_id
    user = await NTEUser.get_scratch_user(target_user_id, state.bot_id)
    if user is None:
        return _json(False, "尚未绑定刮刮乐账号，请先发送【刮刮乐】完成登录")
    if not user.wm_cookie:
        return _json(False, "尚未绑定刮刮乐 Cookie，请先发送【刮刮乐登录】")

    image, error = await build_scratch_report(
        user,
        days,
        cap_ticket=payload.capTicket,
        sec_code=payload.secCode,
    )
    # 滑块/登录/网络类错误可重试；查询成功（含“暂无记录”）则计入限频并让链接一次性失效
    if image is None and error != ScratchMsg.EMPTY:
        return _json(False, error)
    _record_query_done(state.user_id)
    SCRATCH_LOGIN_CACHE.pop(payload.auth)
    if image is None:
        return _json(False, error)
    sent = await _send_qq(state, image)
    if not sent:
        return _json(False, "战报生成成功，但发送到 QQ 失败，请稍后重试")
    return _json(True, "查询完成，战报已发送到 QQ")


async def _proxy_wanmei_cookie(auth: str) -> str:
    """验证码中转：按 auth 解析用户已绑定的完美世界 Cookie。"""
    state = SCRATCH_LOGIN_CACHE.get(auth)
    if state is None:
        return ""
    target_user_id = state.target_user_id or state.user_id
    user = await NTEUser.get_scratch_user(target_user_id, state.bot_id)
    return user.wm_cookie if user is not None else ""


def _unwrap_jsonp(text: str) -> dict:
    raw = text.strip()
    if raw.startswith("cb(") and raw.endswith(")"):
        raw = raw[3:-1]
    try:
        data = json.loads(raw)
        return data if isinstance(data, dict) else {"code": 1, "message": "验证码服务异常"}
    except json.JSONDecodeError:
        return {"code": 1, "message": "验证码服务异常", "raw": raw[:200]}


def _cap_headers(cookie: str) -> dict:
    return {
        "User-Agent": _PROXY_UA,
        "Cookie": cookie,
        "Referer": "https://kf.wanmei.com/selfItemFlowQuery?gameId=191",
        "Accept": "*/*",
    }


@app.post("/nte/scratch/mCaptchaProxy/key")
async def scratch_mcaptcha_key(payload: _CapKeyPayload) -> JSONResponse:
    """手机端无法直连 captchas.wanmei.com 时，由服务器代取验证码 key。"""
    cookie = await _proxy_wanmei_cookie(payload.auth)
    if not cookie:
        return _json(False, "登录状态失效，请重新发送【刮刮乐】")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        resp = await client.get(
            f"{_CAPTCHA_API}/mCaptcha/key",
            params={"appId": payload.appId, "capTicket": payload.capTicket, "callback": "cb"},
            headers=_cap_headers(cookie),
        )
    return JSONResponse(_unwrap_jsonp(resp.text))


@app.post("/nte/scratch/mCaptchaProxy/info")
async def scratch_mcaptcha_info(payload: _CapInfoPayload) -> JSONResponse:
    """服务器代取验证码拼图数据，并把图片地址改走本地中转。"""
    cookie = await _proxy_wanmei_cookie(payload.auth)
    if not cookie:
        return _json(False, "登录状态失效，请重新发送【刮刮乐】")
    async with httpx.AsyncClient(timeout=15, follow_redirects=False, trust_env=False) as client:
        resp = await client.get(
            f"{_CAPTCHA_API}/mCaptcha/info/{payload.capKey}",
            params={"_": str(int(time.time())), "callback": "cb"},
            headers=_cap_headers(cookie),
        )
    data = _unwrap_jsonp(resp.text)
    if isinstance(data.get("result"), dict) and data["result"].get("img"):
        data["result"]["img"] = "/nte/scratch/mCaptchaProxy/img?u=" + quote(data["result"]["img"], safe="")
    return JSONResponse(data)


@app.post("/nte/scratch/mCaptchaProxy/validate")
async def scratch_mcaptcha_validate(request: Request) -> JSONResponse:
    """服务器代提交滑块验证，返回 secCode。"""
    raw = (await request.body()).decode("utf-8", "replace")
    body: dict = {}
    try:
        body = json.loads(raw or "{}")
    except Exception:
        # 兼容表单编码发送
        from urllib.parse import parse_qs

        parsed = parse_qs(raw)
        body = {k: (v[0] if len(v) == 1 else v) for k, v in parsed.items()}
    try:
        payload = _CapValidatePayload.model_validate(body)
    except Exception as exc:
        logger.warning(f"[刮刮乐][validate] 参数校验失败: {exc} body={body!r}")
        return _json(False, "参数不完整，请刷新页面重试")
    cookie = await _proxy_wanmei_cookie(payload.auth)
    if not cookie:
        return _json(False, "登录状态失效，请重新发送【刮刮乐】")
    params = {
        "label": payload.label if payload.label is not None else 0,
        "callback": "cb",
    }
    # 组件版本不同字段有差异，只转发实际携带的字段
    for key in ("capKey", "validData", "op", "fp", "appId", "capTicket"):
        val = getattr(payload, key)
        if val is not None:
            params[key] = val
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        resp = await client.get(
            f"{_CAPTCHA_API}/mCaptcha/validate",
            params=params,
            headers=_cap_headers(cookie),
        )
    return JSONResponse(_unwrap_jsonp(resp.text))


@app.get("/nte/scratch/mCaptchaProxy/img")
async def scratch_mcaptcha_img(u: str) -> Response:
    """手机网络访问不了验证码图片 CDN 时，由服务器代拉图片。"""
    async with httpx.AsyncClient(timeout=20, trust_env=False) as client:
        resp = await client.get(u, headers={"User-Agent": _PROXY_UA})
    media = resp.headers.get("content-type", "image/png")
    return Response(content=resp.content, media_type=media)
