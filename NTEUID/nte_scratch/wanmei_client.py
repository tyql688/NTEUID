from __future__ import annotations

import json
import uuid
from typing import Any

import httpx

from gsuid_core.logger import logger

from ..utils.sdk.base import SdkError, get_proxy_url


class WanmeiError(SdkError):
    pass


class WanmeiCaptchaError(WanmeiError):
    """官方接口要求滑块验证；业务层可据此走手动验证交互。"""


class WanmeiScratchClient:
    """完美世界官方客服系统「物品流向自助查询」客户端（游戏 191 异环）。

    接口结构来自线上抓包与社区逆向（yuelu-lan/yuelu-lab）：
    `POST /selfItemFlowQuery/search`，multipart/form-data，业务字段 + 按字符拆分的
    `0..N` 数字命名字段（服务端按序拼接还原 query string，改字段必须同步重算）。
    单次查询 startTime ~ endTime 间隔不得超过 7 天，每天每类型最多 100 次。
    """

    BASE_URL = "https://kf.wanmei.com"
    SEARCH_PATH = "/selfItemFlowQuery/search"
    REFERER = "https://kf.wanmei.com/selfItemFlowQuery?gameId=191"
    USER_AGENT = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    )
    timeout: float = 20.0

    # 查询类型「喵呜快报活动记录」对应的固定参数（typeId/itemType/itemSubType/item5）
    TYPE_ID = "29"
    GAME_ID = "191"
    ITEM_TYPE = "13"
    ITEM_SUB_TYPE = "1"
    ITEM5 = "110"

    def __init__(self, cookie: str = "") -> None:
        self.cookie = cookie.strip()

    @staticmethod
    def _enc_time(value: str) -> str:
        return value.replace(" ", "+").replace(":", "%3A")

    def _query_str(
        self,
        *,
        role_id: str,
        start: str,
        end: str,
        page_size: int,
        page_no: int,
        cap_ticket: str = "",
        sec_code: str = "",
    ) -> str:
        return (
            f"capTicket={cap_ticket}&secCode={sec_code}&typeId={self.TYPE_ID}&"
            f"gameId={self.GAME_ID}&server=&roleId={role_id}&itemType={self.ITEM_TYPE}&"
            f"itemSubType={self.ITEM_SUB_TYPE}&item5={self.ITEM5}&item12=&"
            f"startTime={self._enc_time(start)}&endTime={self._enc_time(end)}&"
            f"pageSize={page_size}&pageNo={page_no}&item="
        )

    def _build_body(
        self,
        *,
        role_id: str,
        start: str,
        end: str,
        page_size: int,
        page_no: int,
        cap_ticket: str = "",
        sec_code: str = "",
    ) -> tuple[str, bytes]:
        boundary = f"----NTEWebKitFormBoundary{uuid.uuid4().hex[:16]}"
        fields = [
            ("capTicket", cap_ticket),
            ("secCode", sec_code),
            ("typeId", self.TYPE_ID),
            ("gameId", self.GAME_ID),
            ("server", ""),
            ("roleId", role_id),
            ("itemType", self.ITEM_TYPE),
            ("item1", ""),
            ("itemSubType", self.ITEM_SUB_TYPE),
            ("item4", ""),
            ("item5", self.ITEM5),
            ("item8", ""),
            ("item11", ""),
            ("item12", ""),
            ("startTime", start),
            ("endTime", end),
            ("pageSize", str(page_size)),
            ("pageNo", str(page_no)),
            ("item", ""),
        ]
        query_str = self._query_str(
            role_id=role_id,
            start=start,
            end=end,
            page_size=page_size,
            page_no=page_no,
            cap_ticket=cap_ticket,
            sec_code=sec_code,
        )
        lines = [
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            for name, value in fields
        ]
        lines.extend(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{i}"\r\n\r\n{ch}\r\n'
            for i, ch in enumerate(query_str)
        )
        lines.append(f"--{boundary}--\r\n")
        return boundary, "".join(lines).encode("utf-8")

    async def search(
        self,
        role_id: str,
        start: str,
        end: str,
        *,
        page_size: int = 1000,
        page_no: int = 1,
        cap_ticket: str = "",
        sec_code: str = "",
    ) -> dict[str, Any]:
        if not self.cookie:
            raise WanmeiError("刮刮乐 Cookie 为空，请先绑定")
        boundary, body = self._build_body(
            role_id=role_id,
            start=start,
            end=end,
            page_size=page_size,
            page_no=page_no,
            cap_ticket=cap_ticket,
            sec_code=sec_code,
        )
        headers = {
            "User-Agent": self.USER_AGENT,
            "Accept": "*/*",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "x-requested-with": "XMLHttpRequest",
            "Referer": self.REFERER,
            "Cookie": self.cookie,
        }
        proxy = get_proxy_url() or None
        logger.debug(
            f"[NTE-刮刮乐] → POST {self.SEARCH_PATH} roleId={role_id} {start} ~ {end} page={page_no} size={page_size}"
        )
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                proxy=proxy,
                trust_env=False,
                follow_redirects=False,
            ) as client:
                resp = await client.post(
                    f"{self.BASE_URL}{self.SEARCH_PATH}",
                    headers=headers,
                    content=body,
                )
        except httpx.HTTPError as err:
            logger.debug(f"[NTE-刮刮乐] ✗ 网络错误: {err!r}")
            raise WanmeiError("刮刮乐查询网络请求失败") from err

        logger.debug(f"[NTE-刮刮乐] ← HTTP={resp.status_code}")
        if resp.status_code in (301, 302, 303, 307, 308):
            location = resp.headers.get("location", "")
            raise WanmeiError(
                "刮刮乐 Cookie 已失效，请重新绑定",
                {"status_code": resp.status_code, "location": location},
            )
        if resp.status_code >= 400:
            raise WanmeiError(
                f"刮刮乐查询 HTTP {resp.status_code}",
                {"status_code": resp.status_code, "text": resp.text[:200]},
            )
        try:
            payload = resp.json()
        except json.JSONDecodeError as err:
            if "离线" in resp.text or "登录" in resp.text:
                raise WanmeiError(
                    "刮刮乐 Cookie 已失效，请重新绑定",
                    {"status_code": resp.status_code, "text": resp.text[:200]},
                ) from err
            raise WanmeiError("刮刮乐查询响应格式异常", {"text": resp.text[:200]}) from err

        if not isinstance(payload, dict) or payload.get("code") != 0:
            message = ""
            if isinstance(payload, dict):
                message = str(payload.get("message") or payload.get("msg") or "")
            if "验证码" in message or "滑块" in message or "滑动" in message:
                raise WanmeiCaptchaError(message or "需要滑块验证", payload)
            raise WanmeiError(message or "刮刮乐查询失败", payload)

        data = payload.get("data")
        return data if isinstance(data, dict) else {}
