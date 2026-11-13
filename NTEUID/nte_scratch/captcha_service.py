from __future__ import annotations

import io
import json
import math
import random
import asyncio
from base64 import b64encode

from PIL import Image
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

from gsuid_core.logger import logger

from ..utils.sdk.wanmei import WanmeiKfClient, WanmeiCaptchaClient
from ..utils.sdk.wanmei_model import WanmeiError


def _encrypt(value: object, cap_ticket: str) -> str:
    key = (cap_ticket[1:3] + cap_ticket[10:13] + cap_ticket[20:22] + cap_ticket[26:31] + cap_ticket[21:25]).encode()
    text = json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode()
    cipher = AES.new(key, AES.MODE_CBC, iv=key)
    return b64encode(cipher.encrypt(pad(text, AES.block_size))).decode()


def _find_gap(image_bytes: bytes, order: list[int]) -> tuple[int, float]:
    with Image.open(io.BytesIO(image_bytes)) as source:
        image = source.convert("RGBA")
    base = Image.new("RGBA", (260, 120))
    for index, source_index in enumerate(order):
        source_x = source_index % 20 * 13
        source_y = source_index // 20 * 60
        target_x = index % 20 * 13
        target_y = index // 20 * 60
        base.paste(
            image.crop((source_x, source_y, source_x + 13, source_y + 60)),
            (target_x, target_y),
        )

    piece = image.crop((260, 0, 321, 120)).getchannel("A")
    alpha = piece.tobytes()
    gray = base.convert("L").tobytes()
    shape = {(x, y) for x in range(piece.width) for y in range(piece.height) if alpha[y * piece.width + x] > 128}
    ring: set[tuple[int, int]] = set()
    for x, y in shape:
        for delta_x in range(-3, 4):
            for delta_y in range(-3, 4):
                point = (x + delta_x, y + delta_y)
                if point not in shape and 0 <= point[0] < 61 and 0 <= point[1] < 120:
                    ring.add(point)

    best_x = 0
    best_score = -math.inf
    for offset in range(200):
        inside = sum(gray[y * base.width + offset + x] for x, y in shape) / len(shape)
        outside = sum(gray[y * base.width + offset + x] for x, y in ring) / len(ring)
        score = (outside - inside) * max(outside - 150, 1)
        if score > best_score:
            best_x = offset
            best_score = score
    return best_x, best_score


def _drag_trace(distance: int) -> tuple[list[list[float | int]], int]:
    start_x = random.randint(500, 900)
    start_y = random.randint(300, 600)
    trace: list[list[float | int]] = [[start_x, start_y, 1, 0]]
    elapsed_ms = 0
    overshoot = distance + random.uniform(3, 9)
    steps = random.randint(8, 12)
    for index in range(1, steps + 1):
        elapsed_ms += random.randint(95, 140)
        ease = 1 - (1 - index / steps) ** 2.4
        trace.append(
            [
                round(start_x + overshoot * ease + random.uniform(-0.75, 0.75), 1),
                round(start_y + random.uniform(-1.25, 1.25), 1),
                3,
                elapsed_ms,
            ]
        )
    back_steps = random.randint(2, 3)
    for index in range(1, back_steps + 1):
        elapsed_ms += random.randint(100, 160)
        trace.append(
            [
                round(start_x + overshoot + (distance - overshoot) * index / back_steps, 1),
                round(start_y + random.uniform(-0.75, 0.75), 1),
                3,
                elapsed_ms,
            ]
        )
    elapsed_ms += random.randint(70, 200)
    trace.append([start_x + distance, start_y, 2, elapsed_ms])
    return trace, elapsed_ms


async def solve_captcha(kf_client: WanmeiKfClient) -> tuple[str, str]:
    captcha_client = WanmeiCaptchaClient()
    for attempt in range(1, 6):
        cap_ticket = await kf_client.query_cap_ticket()
        cap_key, order, image_bytes = await captcha_client.challenge(cap_ticket)
        gap_x, score = await asyncio.to_thread(_find_gap, image_bytes, order)
        trace, elapsed_ms = _drag_trace(gap_x)
        await asyncio.sleep(elapsed_ms / 1000)
        sec_code = await captcha_client.validate(
            cap_key=cap_key,
            valid_data=_encrypt(
                {"length": gap_x + 9, "validateTimeMilSec": elapsed_ms},
                cap_ticket,
            ),
            operation=_encrypt(trace, cap_ticket),
        )
        logger.debug(
            f"[NTE刮刮乐] 滑块 attempt={attempt} gap_x={gap_x} score={score:.2f} "
            f"elapsed_ms={elapsed_ms} success={sec_code is not None}"
        )
        if sec_code is not None:
            return cap_ticket, sec_code
    raise WanmeiError("客服滑块验证失败，请稍后重试")
