from __future__ import annotations

import json
from typing import Any, Dict, Type, Callable, ClassVar, Optional

import httpx

from gsuid_core.logger import logger

_proxy_provider: Optional[Callable[[], str]] = None


def set_proxy_provider(fn: Optional[Callable[[], str]]) -> None:
    """业务层启动时注入：避免 SDK 反向 import 配置层；fn 返回空字符串即直连。"""
    global _proxy_provider
    _proxy_provider = fn


class SdkError(RuntimeError):
    def __init__(self, message: str, raw: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.message = message
        self.raw = raw


class BaseSdkClient:
    BASE_URL: ClassVar[str] = ""
    USER_AGENT: ClassVar[str] = ""
    error_cls: ClassVar[Type[SdkError]] = SdkError
    timeout: float = 20.0

    def _default_headers(self) -> Dict[str, str]:
        return {"User-Agent": self.USER_AGENT}

    def _finalize_headers(
        self,
        path: str,
        *,
        method: str,
        body: Optional[Dict[str, Any]],
        query: Optional[Dict[str, Any]],
        headers: Dict[str, str],
    ) -> Dict[str, str]:
        return headers

    def _extract_data(self, payload: Dict[str, Any], path: str) -> Any:
        """默认按 `{code, msg, data}` 解析；子类如果字段名不同需自行覆盖。"""
        if payload.get("code") not in (0, "0"):
            raise self.error_cls(f"[{path}] {payload.get('msg', '')}", payload)
        return payload["data"] if "data" in payload and payload["data"] is not None else {}

    async def _request(
        self,
        path: str,
        *,
        method: str = "GET",
        body: Optional[Dict[str, Any]] = None,
        query: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        """JSON dict 响应走 `_extract_data`；异常响应、空响应、非 JSON 响应统一抛 SDK 错误。"""
        merged = dict(self._default_headers())
        if headers is not None:
            merged.update(headers)
        if body is not None:
            merged.setdefault("Content-Type", "application/x-www-form-urlencoded")
        merged = self._finalize_headers(
            path,
            method=method,
            body=body,
            query=query,
            headers=merged,
        )

        tag = self.__class__.__name__
        logger.debug(f"[NTE-SDK] → {tag} {method} {self.BASE_URL}{path} query={query} body={body} headers={merged}")

        proxy: Optional[str] = None
        if _proxy_provider:
            candidate = _proxy_provider()
            if candidate:
                proxy = candidate
        try:
            async with httpx.AsyncClient(timeout=self.timeout, proxy=proxy, trust_env=False) as client:
                resp = await client.request(
                    method,
                    f"{self.BASE_URL}{path}",
                    headers=merged,
                    params=query,
                    data=body,
                )
        except httpx.HTTPError as err:
            logger.debug(f"[NTE-SDK] ✗ {tag} {method} {path} 网络错误: {err!r}")
            raise self.error_cls(f"[{path}] 网络请求失败") from err

        logger.debug(f"[NTE-SDK] ← {tag} {method} {path} HTTP={resp.status_code} body={resp.text}")

        if resp.status_code >= 400:
            raise self.error_cls(
                f"[{path}] HTTP {resp.status_code}",
                {"status_code": resp.status_code, "text": resp.text},
            )
        if not resp.content:
            raise self.error_cls(f"[{path}] 响应为空", {"status_code": resp.status_code})

        try:
            payload = resp.json()
        except json.JSONDecodeError:
            return resp.text
        return self._extract_data(payload, path) if isinstance(payload, dict) else payload
