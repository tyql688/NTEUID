from __future__ import annotations

import re
from dataclasses import asdict

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse, RedirectResponse

from gsuid_core.logger import logger
from gsuid_core.web_app import app

from ..utils.msgs import LoginMsg
from .login_service import (
    LOGIN_CACHE,
    LoginState,
    LoginResult,
    perform_login,
    send_login_sms,
    mark_login_failed,
)
from ..utils.sdk.laohu import LaohuError
from ..utils.resource.RESOURCE_PATH import NTE_TEMPLATES

_MOBILE_RE = re.compile(r"^1\d{10}$")
_CODE_RE = re.compile(r"^\d{4,8}$")


def _json(result: LoginResult) -> JSONResponse:
    return JSONResponse(asdict(result), status_code=200 if result.ok else 400)


def _login_user_id(auth_token: str) -> str:
    state: LoginState | None = LOGIN_CACHE.get(auth_token)
    return state.user_id if state else "unknown"


class _SendSmsPayload(BaseModel):
    auth: str
    mobile: str


class _LoginPayload(BaseModel):
    auth: str
    mobile: str
    code: str


@app.get("/nte/i/{auth_token}")
async def nte_login_page(auth_token: str):
    state: LoginState | None = LOGIN_CACHE.get(auth_token)
    if not state:
        return HTMLResponse(LoginMsg.link_expired(), status_code=404)
    if state.ok:
        return RedirectResponse("/nte/done", status_code=303)
    return HTMLResponse(
        NTE_TEMPLATES.get_template("login.html").render(
            auth=auth_token,
            user_id=state.user_id,
            msg={
                "smsSent": LoginMsg.SMS_SENT,
                "smsSendFailed": LoginMsg.SMS_SEND_FAILED,
                "loginSuccess": LoginMsg.SMS_VERIFIED,
                "loginFailed": LoginMsg.USER_CENTER_LOGIN_FAILED,
            },
        )
    )


@app.get("/nte/done")
async def nte_login_done() -> HTMLResponse:
    return HTMLResponse(NTE_TEMPLATES.get_template("done.html").render())


@app.post("/nte/sendSmsCode")
async def nte_send_sms(payload: _SendSmsPayload, _request: Request) -> JSONResponse:
    if not _MOBILE_RE.match(payload.mobile):
        return _json(LoginResult.fail(LoginMsg.MOBILE_INVALID))

    try:
        return _json(await send_login_sms(payload.auth, payload.mobile))
    except LaohuError as error:
        logger.warning(f"[NTE登录] 短信下发失败 user_id={_login_user_id(payload.auth)}: {error.message}")
        return _json(LoginResult.fail(LoginMsg.SMS_SEND_FAILED))


@app.post("/nte/login")
async def nte_perform_login(payload: _LoginPayload, _request: Request) -> JSONResponse:
    if not _MOBILE_RE.match(payload.mobile):
        return _json(LoginResult.fail(LoginMsg.MOBILE_INVALID))
    if not _CODE_RE.match(payload.code):
        return _json(LoginResult.fail(LoginMsg.CODE_INVALID))

    # 塔吉多登录原子搬到了命令段（login_by_laohu_token），TajiduoError 不会从这里冒出来；
    # 这里只兜短信验证阶段的 LaohuError。
    try:
        return _json(await perform_login(payload.auth, payload.mobile, payload.code))
    except LaohuError as error:
        mark_login_failed(payload.auth, LoginMsg.SMS_LOGIN_FAILED)
        logger.warning(f"[NTE登录] 老虎短信登录失败 user_id={_login_user_id(payload.auth)}: {error.message}")
        return _json(LoginResult.fail(LoginMsg.SMS_LOGIN_FAILED))


@app.get("/nte/status/{auth_token}")
async def nte_login_status(auth_token: str) -> JSONResponse:
    state: LoginState | None = LOGIN_CACHE.get(auth_token)
    if not state:
        return JSONResponse({"status": "expired"})
    return JSONResponse(
        {
            "status": state.status,
            "ok": state.ok,
            "msg": state.msg,
        }
    )
