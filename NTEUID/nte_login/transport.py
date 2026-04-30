from __future__ import annotations

import hmac
import json
import time
import asyncio
import hashlib
from typing import Protocol
from dataclasses import dataclass
from collections.abc import Callable

import httpx
from pydantic import Field, BaseModel, ConfigDict

from gsuid_core.logger import logger

from ..nte_config.nte_config import NTEConfig

START_TIMEOUT_S = 10.0
POLL_INTERVAL_S = 2.0


def _login_ttl_s() -> int:
    return NTEConfig.get_config("NTELoginTTL").data


@dataclass(frozen=True)
class TransportResult:
    status: str  # success | failed | expired
    msg: str = ""
    laohu_token: str = ""
    laohu_user_id: str = ""


class TransportError(RuntimeError):
    pass


class _ProtocolModel(BaseModel):
    """nte-login 服务回执的解析基类。"""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")


class _Credential(_ProtocolModel):
    laohu_token: str = Field(description="老虎用户中心 token")
    laohu_user_id: str = Field(description="老虎用户中心 userId（数字字符串）")


class _StatusModel(_ProtocolModel):
    status: str = Field(description="pending / success / failed / expired / heartbeat")
    msg: str = Field(default="", description="给用户看的展示文案")
    credential: _Credential | None = Field(default=None, description="终态为 success 时的凭据")


class LoginTransport(Protocol):
    async def start(
        self,
        *,
        auth: str,
        user_id: str,
        bot_id: str,
        group_id: str | None,
    ) -> str: ...

    async def listen(self, auth: str) -> TransportResult | None: ...


def _secret() -> str:
    return NTEConfig.get_config("NTELoginSecret").data.strip()


def _sign(parts: list[str]) -> str:
    secret = _secret()
    if not secret:
        return ""
    return hmac.new(secret.encode(), "|".join(parts).encode(), hashlib.sha256).hexdigest()


def _to_result(payload: _StatusModel) -> TransportResult | None:
    """终态才返回 TransportResult；pending / heartbeat 等中间态返回 None。"""
    if payload.status not in {"success", "failed", "expired"}:
        return None
    cred = payload.credential
    return TransportResult(
        status=payload.status,
        msg=payload.msg,
        laohu_token=cred.laohu_token if cred else "",
        laohu_user_id=cred.laohu_user_id if cred else "",
    )


def _normalize_base_url(raw: str) -> str:
    """与 `_login_page_url` 一致：没带 scheme 自动补 https；尾斜杠去掉。"""
    raw = raw.strip().rstrip("/")
    if not raw.startswith(("http://", "https://")):
        raw = f"https://{raw}"
    return raw


class _Base:
    def __init__(self, base_url: str):
        self.base_url = _normalize_base_url(base_url)

    async def start(
        self,
        *,
        auth: str,
        user_id: str,
        bot_id: str,
        group_id: str | None,
    ) -> str:
        ts = int(time.time())
        body = {
            "auth": auth,
            "user_id": user_id,
            "bot_id": bot_id,
            "group_id": group_id,
            "ts": ts,
            "sig": _sign(["start", auth, user_id, str(ts)]),
        }
        url = f"{self.base_url}/nte/start"
        logger.debug(f"[NTE-LOGIN] POST {url} body={body}")
        try:
            async with httpx.AsyncClient(timeout=START_TIMEOUT_S, trust_env=False) as client:
                resp = await client.post(url, json=body)
        except httpx.HTTPError as err:
            raise TransportError(f"外置登录服务网络错误 url={url}: {err!r}") from err

        if resp.status_code != 200:
            raise TransportError(f"外置登录服务 start 返回 HTTP {resp.status_code} url={url}: {resp.text or '<empty>'}")

        # 登录页 URL 由 NTEUID 自己用 base_url 拼，nte-login 不再回传
        return f"{self.base_url}/nte/i/{auth}"


class HttpPollTransport(_Base):
    async def listen(self, auth: str) -> TransportResult | None:
        waited_s = 0.0
        async with httpx.AsyncClient(timeout=START_TIMEOUT_S, trust_env=False) as client:
            while waited_s < _login_ttl_s():
                ts = int(time.time())
                params = {"ts": ts, "sig": _sign(["listen", auth, str(ts)])}
                try:
                    resp = await client.get(f"{self.base_url}/nte/status/{auth}", params=params)
                except httpx.HTTPError as err:
                    logger.debug(f"[NTE-LOGIN] poll 网络错误，将重试: {err!r}")
                    await asyncio.sleep(POLL_INTERVAL_S)
                    waited_s += POLL_INTERVAL_S
                    continue
                if resp.status_code != 200:
                    raise TransportError(f"poll 返回 HTTP {resp.status_code}: {resp.text}")

                payload = _StatusModel.model_validate_json(resp.text)
                terminal = _to_result(payload)
                if terminal is not None:
                    return terminal
                await asyncio.sleep(POLL_INTERVAL_S)
                waited_s += POLL_INTERVAL_S
        return None


class SseTransport(_Base):
    async def listen(self, auth: str) -> TransportResult | None:
        wait_s = _login_ttl_s()
        ts = int(time.time())
        params = {"ts": ts, "sig": _sign(["listen", auth, str(ts)])}
        url = f"{self.base_url}/nte/events/{auth}"
        # 服务端心跳会重置 httpx 的 idle timer，所以 httpx.Timeout 不能保证绝对超时；
        # 套一层 asyncio.timeout 做硬截断，跟 ws 行为对齐。
        timeout = httpx.Timeout(wait_s, connect=START_TIMEOUT_S)
        try:
            async with asyncio.timeout(wait_s):
                async with httpx.AsyncClient(timeout=timeout, trust_env=False) as client:
                    async with client.stream("GET", url, params=params) as response:
                        if response.status_code != 200:
                            body = await response.aread()
                            raise TransportError(
                                f"SSE 握手失败 HTTP {response.status_code}: {body.decode(errors='ignore')}"
                            )
                        return await self._consume_sse(response)
        except TimeoutError:
            return None
        except httpx.HTTPError as err:
            raise TransportError(f"SSE 网络错误: {err!r}") from err

    @staticmethod
    async def _consume_sse(response: httpx.Response) -> TransportResult | None:
        buffer: list[str] = []
        async for line in response.aiter_lines():
            if line.startswith(":"):
                continue  # SSE 注释行（心跳）
            if line == "":
                if not buffer:
                    continue
                raw = "".join(buffer)
                buffer.clear()
                payload = _StatusModel.model_validate(json.loads(raw))
                terminal = _to_result(payload)
                if terminal is not None:
                    return terminal
                continue
            if line.startswith("data:"):
                buffer.append(line[5:].lstrip())
        return None


class WsTransport(_Base):
    async def listen(self, auth: str) -> TransportResult | None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as err:
            raise TransportError("ws 模式需要安装 `websockets` 库") from err

        ts = int(time.time())
        ws_base = self.base_url.replace("https://", "wss://", 1).replace("http://", "ws://", 1)
        url = f"{ws_base}/nte/ws/{auth}?ts={ts}&sig={_sign(['listen', auth, str(ts)])}"

        try:
            async with asyncio.timeout(_login_ttl_s()):
                async with connect(url, open_timeout=START_TIMEOUT_S, proxy=None) as ws:
                    async for raw in ws:
                        payload = _StatusModel.model_validate(json.loads(raw))
                        terminal = _to_result(payload)
                        if terminal is not None:
                            return terminal
        except TimeoutError:
            return None
        except OSError as err:
            raise TransportError(f"ws 连接失败: {err!r}") from err
        return None


_TRANSPORTS: dict[str, Callable[[str], LoginTransport]] = {
    "http_poll": HttpPollTransport,
    "sse": SseTransport,
    "ws": WsTransport,
}


def build_transport(base_url: str) -> LoginTransport:
    name = NTEConfig.get_config("NTELoginTransport").data.strip()
    factory = _TRANSPORTS.get(name)
    if factory is None:
        raise TransportError(f"未知 transport：{name}（可选：{', '.join(_TRANSPORTS)}）")
    return factory(base_url)
