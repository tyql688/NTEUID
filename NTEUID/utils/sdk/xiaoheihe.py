from __future__ import annotations

import re
import time
import base64
import random
import hashlib
import binascii
from typing import Any

from .base import BaseSdkClient
from ..constants import XIAOHEIHE_BASE_URL
from .xiaoheihe_model import (
    XiaoheiheError,
    LotteryAnalysis,
    _parse,
    _expect_dict,
)


def _get_hkey(url_path: str, timestamp: int, nonce: str) -> str:
    def iv(e: str, t: str, n: int | None = None) -> str:
        src = t[:n] if n is not None else t
        return "".join(src[ord(c) % len(src)] for c in e)

    def vm(x: int) -> int:
        return 255 & ((x << 1) ^ 27) if x & 128 else x << 1

    def qm(x: int) -> int:
        return vm(x) ^ x

    def dm(x: int) -> int:
        return qm(vm(x))

    def ym(x: int) -> int:
        return dm(qm(vm(x)))

    def gm(x: int) -> int:
        return ym(x) ^ dm(x) ^ qm(x)

    def km(e: list[int]) -> list[int]:
        result = list(e)
        result[0] = gm(e[0]) ^ ym(e[1]) ^ dm(e[2]) ^ qm(e[3])
        result[1] = qm(e[0]) ^ gm(e[1]) ^ ym(e[2]) ^ dm(e[3])
        result[2] = dm(e[0]) ^ qm(e[1]) ^ gm(e[2]) ^ ym(e[3])
        result[3] = ym(e[0]) ^ dm(e[1]) ^ qm(e[2]) ^ gm(e[3])
        return result

    charset = "AB45STUVWZEFGJ6CH01D237IXYPQRKLMN89"
    parts = [p for p in url_path.split("/") if p]
    normalized_path = "/" + "/".join(parts) + "/"

    comp1 = iv(str(timestamp), charset, -2)
    comp2 = iv(normalized_path, charset)
    comp3 = iv(nonce, charset)

    max_len = max(len(c) for c in (comp1, comp2, comp3))
    interleaved = "".join(c[k] for k in range(max_len) for c in (comp1, comp2, comp3) if k < len(c))

    md5_hash = hashlib.md5(interleaved[:20].encode()).hexdigest()
    hkey_prefix = iv(md5_hash[:5], charset, -4)
    checksum = sum(km([ord(c) for c in md5_hash[-6:]])) % 100

    return hkey_prefix + f"{checksum:02d}"


# pkey 格式: base64("timestamp.version_heybox_id_random")


def extract_heybox_id_from_pkey(pkey: str) -> str:
    try:
        decoded = base64.b64decode(pkey + "=" * ((4 - len(pkey) % 4) % 4)).decode("utf-8", errors="replace")
        m = re.match(r"^\d+\.\d+_(\d+)", decoded)
        if m:
            return m.group(1)
    except (binascii.Error, UnicodeDecodeError):
        pass
    return ""


class XiaoheiheClient(BaseSdkClient):
    """小黑盒异环战绩/抽卡数据客户端。

    只接收 pkey，内部自动解码提取 heybox_id。
    使用 PC 网页端参数：x_client_type=weboutapp, x_os_type=Mac。
    """

    BASE_URL = XIAOHEIHE_BASE_URL
    error_cls = XiaoheiheError

    def __init__(
        self,
        *,
        pkey: str = "",
    ) -> None:
        self.pkey = pkey
        self.heybox_id = extract_heybox_id_from_pkey(pkey)

    def _build_query(self, path: str) -> dict[str, Any]:
        timestamp = int(time.time())
        nonce = hashlib.md5(f"{int(time.time() * 1000)}{random.random()}".encode()).hexdigest().upper()
        hkey = _get_hkey(path, timestamp, nonce)
        return {
            "app": "heybox",
            "heybox_id": self.heybox_id,
            "os_type": "web",
            "x_app": "heybox",
            "x_client_type": "weboutapp",
            "x_os_type": "Mac",
            "x_client_version": "",
            "version": "999.0.4",
            "hkey": hkey,
            "_time": str(timestamp),
            "nonce": nonce,
        }

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": "https://www.xiaoheihe.cn/",
            "Accept": "application/json, text/plain, */*",
            "Cookie": f"user_heybox_id={self.heybox_id}; user_pkey={self.pkey}",
        }

    def _extract_data(self, payload: dict[str, Any], path: str) -> Any:
        if payload.get("status") != "ok":
            msg = payload.get("msg", "未知错误")
            raise self.error_cls(f"[{path}] {msg}", payload)
        return payload.get("result", {})

    async def lottery_analysis(self) -> LotteryAnalysis:
        path = "/game/yihuan/player/lottery_analysis"
        err = "小黑盒抽卡数据格式错误"
        data = await self._request(
            path,
            method="GET",
            query=self._build_query(path),
            headers=self._headers(),
        )
        return _parse(LotteryAnalysis, _expect_dict(data, err), err)

    async def player_overview(self) -> dict[str, Any]:
        path = "/game/yihuan/player/overview"
        data = await self._request(
            path,
            method="GET",
            query=self._build_query(path),
            headers=self._headers(),
        )
        return _expect_dict(data, "小黑盒玩家总览格式错误")
