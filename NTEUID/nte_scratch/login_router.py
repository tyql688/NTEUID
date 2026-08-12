from __future__ import annotations

import re

from fastapi import Request
from pydantic import BaseModel
from starlette.responses import HTMLResponse, JSONResponse

from gsuid_core.logger import logger
from gsuid_core.web_app import app

from ..utils.database import NTEUser
from ..utils.msgs import ScratchMsg
from ..utils.resource.RESOURCE_PATH import NTE_TEMPLATES
from .scratch_login import (
    SCRATCH_LOGIN_CACHE,
    ScratchLoginError,
    close_scratch_client,
    fetch_cap_ticket,
    finish_scratch_login,
    scratch_login_page_url,
    send_scratch_sms,
)

_MOBILE_RE = re.compile(r"^1\d{10}$")
_CODE_RE = re.compile(r"^\d{4,8}$")
_NO_CACHE = {"Cache-Control": "no-store, no-cache, must-revalidate"}


def _json(ok: bool, msg: str = "", **extra: object) -> JSONResponse:
    return JSONResponse({"ok": ok, "msg": msg, **extra})


def _state(auth: str):
    state = SCRATCH_LOGIN_CACHE.get(auth)
    if state is None:
        return None, _json(False, "登录链接已失效，请回到 QQ 重新发送【刮刮乐登录】")
    return state, None


class _CapPayload(BaseModel):
    auth: str


class _SmsPayload(BaseModel):
    auth: str
    phone: str
    capTicket: str
    secCode: str


class _LoginPayload(BaseModel):
    auth: str
    phone: str
    code: str
    capTicket: str
    secCode: str


class _BindRolePayload(BaseModel):
    auth: str
    roleId: str
    roleName: str


@app.get("/nte/scratch/{auth_token}")
async def scratch_login_page(auth_token: str) -> HTMLResponse:
    state = SCRATCH_LOGIN_CACHE.get(auth_token)
    if state is None:
        return HTMLResponse("登录链接已失效，请回到 QQ 重新发送【刮刮乐登录】", status_code=404, headers=_NO_CACHE)
    if state.status == "success":
        if state.roles and not state.role_bound:
            buttons = "".join(
                f'<button class="role-btn" data-role="{r["roleId"]}" data-name="{r["roleName"]}">'
                f"{r['roleName']}（{r['roleId']}）</button>"
                for r in state.roles
            )
            return HTMLResponse(
                f"""
                <!DOCTYPE html><html lang="zh-CN"><head><meta charset="UTF-8">
                <meta name="viewport" content="width=device-width, initial-scale=1.0">
                <title>选择角色</title>
                <style>
                  body{{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
                    background:linear-gradient(160deg,#101828,#1e293b);font-family:"PingFang SC","Microsoft YaHei",sans-serif;}}
                  .card{{max-width:420px;width:100%;background:#1b2537;border-radius:18px;padding:28px 24px;color:#fff;
                    box-shadow:0 16px 48px rgba(0,0,0,.45);}}
                  h2{{margin:0 0 8px;font-size:22px;}} p{{color:#94a3b8;font-size:13px;line-height:1.6;}}
                  .role-btn{{display:block;width:100%;margin:10px 0;padding:14px;border:0;border-radius:10px;
                    background:#f59e0b;color:#1e293b;font-size:15px;font-weight:600;cursor:pointer;}}
                  #status{{color:#34d399;font-size:13px;text-align:center;margin-top:12px;}}
                </style></head><body>
                <div class="card"><h2>请选择要绑定的角色</h2>
                <p>检测到该完美世界账号下有多个异环角色，请选择你要查询刮刮乐的角色：</p>
                {buttons}
                <p id="status"></p></div>
                <script>
                  document.querySelectorAll(".role-btn").forEach(function (b) {{
                    b.onclick = async function () {{
                      var r = await fetch("/nte/scratch/bindRole", {{
                        method: "POST", headers: {{"Content-Type": "application/json"}},
                        body: JSON.stringify({{auth: "{auth_token}", roleId: b.dataset.role, roleName: b.dataset.name}})
                      }});
                      var d = await r.json();
                      document.getElementById("status").textContent = d.msg || d.error;
                      if (d.ok && d.queryUrl) {{ location.href = d.queryUrl; }}
                    }};
                  }});
                </script></body></html>
                """,
                headers=_NO_CACHE,
            )
        return HTMLResponse("刮刮乐已绑定成功，请回到 QQ 发送【刮刮乐】开始查询", headers=_NO_CACHE)
    return HTMLResponse(
        NTE_TEMPLATES.get_template("scratch_login.html").render(
            auth=auth_token,
        ),
        headers=_NO_CACHE,
    )


@app.post("/nte/scratch/capTicket")
async def scratch_cap_ticket(payload: _CapPayload) -> JSONResponse:
    if SCRATCH_LOGIN_CACHE.get(payload.auth) is None:
        return _json(False, "登录链接已失效，请重新发送【刮刮乐登录】")
    try:
        cap_ticket = await fetch_cap_ticket(payload.auth)
    except ScratchLoginError as error:
        logger.warning(f"[刮刮乐] 获取验证码失败: {error.message}")
        return _json(False, error.message)
    return _json(True, "", capTicket=cap_ticket, capAppId="20047")


@app.post("/nte/scratch/sendSmsCode")
async def scratch_send_sms(payload: _SmsPayload) -> JSONResponse:
    if SCRATCH_LOGIN_CACHE.get(payload.auth) is None:
        return _json(False, "登录链接已失效，请重新发送【刮刮乐登录】")
    if not _MOBILE_RE.match(payload.phone):
        return _json(False, "手机号格式错误")
    try:
        await send_scratch_sms(payload.auth, payload.phone, payload.capTicket, payload.secCode)
    except ScratchLoginError as error:
        logger.warning(f"[刮刮乐] 短信下发失败: {error.message}")
        return _json(False, error.message)
    return _json(True, "短信验证码已发送，请填写")


@app.post("/nte/scratch/login")
async def scratch_login(payload: _LoginPayload, _request: Request) -> JSONResponse:
    state, err = _state(payload.auth)
    if err is not None:
        return err
    if not _MOBILE_RE.match(payload.phone):
        return _json(False, "手机号格式错误")
    if not _CODE_RE.match(payload.code):
        return _json(False, "验证码格式错误")
    try:
        cookie, roles = await finish_scratch_login(
            payload.auth,
            state.user_id,
            state.bot_id,
            payload.phone,
            payload.code,
            payload.capTicket,
            payload.secCode,
        )
    except ScratchLoginError as error:
        logger.warning(f"[刮刮乐] 网页登录失败 user_id={state.user_id}: {error.message}")
        return _json(False, error.message)
    state.status = "success"
    state.msg = "登录成功"
    state.roles = roles
    if len(roles) == 1:
        role = roles[0]
        await NTEUser.upsert_scratch_role(
            state.user_id, state.bot_id, role["roleId"], role["roleName"], cookie
        )
        state.role_bound = True
        state.roles = None
    SCRATCH_LOGIN_CACHE.set(payload.auth, state)
    close_scratch_client(payload.auth)
    if len(roles) > 1:
        return _json(True, "登录成功，请选择角色", roles=roles)
    return _json(True, "登录成功，请回到 QQ 发送【刮刮乐】开始查询")


@app.post("/nte/scratch/bindRole")
async def scratch_bind_role(payload: _BindRolePayload) -> JSONResponse:
    state, err = _state(payload.auth)
    if err is not None:
        return err
    if state.status != "success":
        return _json(False, "请先完成登录")
    user = await NTEUser.get_scratch_user(state.user_id, state.bot_id)
    cookie = user.wm_cookie if user is not None else ""
    if not cookie:
        return _json(False, "未找到已绑定的完美世界 Cookie，请重新登录")
    await NTEUser.upsert_scratch_role(
        state.user_id, state.bot_id, payload.roleId, payload.roleName, cookie
    )
    state.role_bound = True
    state.roles = None
    SCRATCH_LOGIN_CACHE.set(payload.auth, state)
    query_url = f"{await scratch_login_page_url()}/nte/scratch/query/{payload.auth}"
    return _json(True, "绑定成功", queryUrl=query_url)
