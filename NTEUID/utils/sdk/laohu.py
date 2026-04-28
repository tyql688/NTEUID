from __future__ import annotations

import time
import uuid
import hashlib
from base64 import b64encode
from typing import Any
from dataclasses import field, dataclass

from .base import SdkError, BaseSdkClient

LAOHU_BASE_URL = "https://user.laohu.com"
LAOHU_SDK_VERSION = "4.273.0"
LAOHU_USER_AGENT = "okhttp/4.9.0"
LAOHU_DEFAULT_PACKAGE = "com.pwrd.htassistant"
LAOHU_DEFAULT_VERSION_CODE = 12


class LaohuError(SdkError):
    pass


@dataclass
class LaohuDevice:
    device_id: str = ""
    device_type: str = "Pixel 6"
    device_model: str = "Pixel 6"
    device_name: str = "Pixel 6"
    device_sys: str = "Android 14"
    adm: str = ""
    imei: str = ""
    idfa: str = ""
    mac: str = ""

    def __post_init__(self) -> None:
        if not self.device_id:
            self.device_id = "HT" + uuid.uuid4().hex[:14].upper()
        if not self.adm:
            self.adm = self.device_id


@dataclass(frozen=True)
class LaohuAccount:
    user_id: int
    token: str
    raw: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_payload(cls, data: dict) -> "LaohuAccount":
        raw_user_id = data.get("userId")
        raw_token = data.get("token")
        if raw_user_id is None or raw_token is None:
            raise LaohuError("老虎登录返回缺少 userId/token", data)
        token = str(raw_token)
        if not token:
            raise LaohuError("老虎登录返回 token 为空", data)
        try:
            user_id = int(raw_user_id)
        except (TypeError, ValueError) as err:
            raise LaohuError("老虎登录返回 userId 格式错误", data) from err
        if user_id <= 0:
            raise LaohuError("老虎登录返回 userId 无效", data)
        return cls(
            user_id=user_id,
            token=token,
            raw=data,
        )


class LaohuClient(BaseSdkClient):
    BASE_URL = LAOHU_BASE_URL
    USER_AGENT = LAOHU_USER_AGENT
    error_cls = LaohuError

    def __init__(
        self,
        app_id: int,
        app_key: str,
        *,
        channel_id: int = 1,
        package: str = LAOHU_DEFAULT_PACKAGE,
        version_code: int = LAOHU_DEFAULT_VERSION_CODE,
        device: LaohuDevice | None = None,
        timeout: float = BaseSdkClient.timeout,
    ):
        if len(app_key) < 16:
            raise ValueError("app_key 长度必须 >= 16")
        self.app_id = app_id
        self.app_key = app_key
        self.channel_id = channel_id
        self.package = package
        self.version_code = version_code
        self.device = device if device is not None else LaohuDevice()
        self.timeout = timeout
        self._aes_key = app_key[-16:].encode()

    def _aes_encrypt(self, plain: str) -> str:
        from Crypto.Cipher import AES
        from Crypto.Util.Padding import pad

        cipher = AES.new(self._aes_key, AES.MODE_ECB)
        return b64encode(cipher.encrypt(pad(plain.encode(), AES.block_size))).decode()

    def _sign(self, params: dict[str, str]) -> str:
        raw = "".join(params[key] for key in sorted(params)) + self.app_key
        return hashlib.md5(raw.encode()).hexdigest()

    def _common_fields(self, *, use_millis: bool) -> dict[str, str]:
        device = self.device
        ts = int(time.time() * 1000) if use_millis else int(time.time())
        base = {
            "appId": str(self.app_id),
            "channelId": str(self.channel_id),
            "deviceId": device.device_id,
            "deviceType": device.device_type,
            "deviceModel": device.device_model,
            "deviceName": device.device_name,
            "deviceSys": device.device_sys,
            "adm": device.adm,
            "idfa": device.idfa,
            "sdkVersion": LAOHU_SDK_VERSION,
            "bid": self.package,
            "t": str(ts),
        }
        if use_millis:
            base["version"] = str(self.version_code)
            base["mac"] = device.mac
        else:
            base["versionCode"] = str(self.version_code)
            base["imei"] = device.imei
        return base

    def _extract_data(self, payload: dict[str, Any], path: str) -> Any:
        """laohu 用 `{code, message, result}` 结构（字段名和 base 不一样，必须覆盖）。"""
        if payload.get("code") not in (0, "0"):
            raise self.error_cls(f"[{path}] {payload.get('message', '')}", payload)
        return payload["result"] if "result" in payload and payload["result"] is not None else {}

    async def _submit(
        self,
        path: str,
        params: dict[str, str],
        *,
        method: str = "POST",
        keep_empty: bool = False,
    ) -> Any:
        signed = dict(params)
        signed["sign"] = self._sign(signed)  # 注意：签名要在过滤前，否则签名值会和服务端对不上
        cleaned = {k: v for k, v in signed.items() if v is not None and (keep_empty or v != "")}
        if method == "GET":
            return await self._request(path, method="GET", query=cleaned)
        return await self._request(path, method="POST", body=cleaned)

    async def list_area_codes(self) -> list[dict]:
        params = self._common_fields(use_millis=False)
        return await self._submit("/m/newApi/areaCode/list", params, method="GET")

    async def send_sms_code(
        self,
        cellphone: str,
        *,
        area_code_id: str = "1",
        sms_type: int = 16,
    ) -> None:
        params = self._common_fields(use_millis=False)
        params["cellphone"] = cellphone
        params["areaCodeId"] = area_code_id
        params["type"] = str(sms_type)
        await self._submit("/m/newApi/sendPhoneCaptchaWithOutLogin", params)

    async def check_sms_code(self, cellphone: str, code: str) -> None:
        params = self._common_fields(use_millis=False)
        params["cellphone"] = cellphone
        params["captcha"] = code
        await self._submit("/m/newApi/checkPhoneCaptchaWithOutLogin", params)

    async def login_by_sms(
        self,
        cellphone: str,
        code: str,
        *,
        area_code_id: str = "1",
        sms_type: int = 16,
        skip_check: bool = False,
    ) -> LaohuAccount:
        if not skip_check:
            await self.check_sms_code(cellphone, code)

        params = self._common_fields(use_millis=True)
        params["cellphone"] = self._aes_encrypt(cellphone)
        params["captcha"] = self._aes_encrypt(code)
        params["areaCodeId"] = area_code_id
        params["type"] = str(sms_type)

        result = await self._submit("/openApi/sms/new/login", params, keep_empty=True)
        return LaohuAccount.from_payload(result)
