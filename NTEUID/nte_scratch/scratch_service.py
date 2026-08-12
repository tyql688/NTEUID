from __future__ import annotations

import asyncio
import re
import time as _time
from datetime import date, datetime, timedelta
from typing import Any

from gsuid_core.bot import Bot
from gsuid_core.logger import logger
from gsuid_core.models import Event

from ..utils.at import AtTarget, resolve_at_target
from ..utils.cache import TimedCache
from ..utils.database import NTEGroupMember, NTEUser
from ..utils.msgs import ScratchMsg, send_nte_notify
from .scratch_card import draw_scratch_card_img, draw_scratch_rank_img
from .scratch_login import (
    SCRATCH_LOGIN_TTL,
    ScratchLoginError,
    begin_scratch_login,
    scratch_login_page_url,
    _kf_session_cookie,
)
from .wanmei_client import WanmeiCaptchaError, WanmeiError, WanmeiScratchClient

TAG = "刮刮乐"

# 刮刮乐 = 购买读物附赠刮刮卡；读物售价决定单次消耗
SCRATCH_CARD_COSTS: dict[str, int] = {
    "《荧幕之外》": 10_000,
    "《海特洛快讯》": 20_000,
    "《猫会梦见什么》": 50_000,
    "《拉面的艺术》": 50_000,
    "《在书本之外》": 50_000,
}
DEFAULT_COST = 50_000
BIG_AWARD = 200_000  # 大奖档位（≥20 万方斯）

# 查询结果图片 120 秒内存缓存，降低重复查询延迟与官方接口压力
RESULT_CACHE: TimedCache = TimedCache(timeout=120, maxsize=64)

_query_locks: dict[str, asyncio.Lock] = {}
_QUERY_HISTORY: dict[str, list[float]] = {}
QUERY_MIN_INTERVAL = 60  # 同用户两次成功查询的最小间隔（秒）
QUERY_DAILY_LIMIT = 30   # 每用户每天成功查询上限（官方每日每类型 100 次）

_FANGSI_RE = re.compile(r"方斯\s*[*×xX]\s*([0-9][0-9,]*)")
_NUMBER_RE = re.compile(r"([0-9][0-9,]*)")


def _user_lock(user_id: str) -> asyncio.Lock:
    lock = _query_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _query_locks[user_id] = lock
    return lock


def _check_query_limit(user_id: str) -> tuple[bool, str]:
    """刮刮乐查询限频：防连点 + 每日上限，成功查询才计入。"""
    now = _time.time()
    times = [t for t in _QUERY_HISTORY.get(user_id, []) if now - t < 86400]
    if len(times) >= QUERY_DAILY_LIMIT:
        return False, f"今日刮刮乐查询已达上限（{QUERY_DAILY_LIMIT} 次），请明天再试"
    if times and now - times[-1] < QUERY_MIN_INTERVAL:
        left = QUERY_MIN_INTERVAL - int(now - times[-1])
        return False, f"查询太频繁，请 {left} 秒后再试"
    return True, ""


def _record_query_done(user_id: str) -> None:
    now = _time.time()
    times = [t for t in _QUERY_HISTORY.get(user_id, []) if now - t < 86400]
    times.append(now)
    _QUERY_HISTORY[user_id] = times


def _parse_days(text: str) -> int:
    match = re.search(r"(\d{1,2})\s*天?", text or "")
    if match:
        return max(1, min(60, int(match.group(1))))
    return 60


def _split_segments(start: date, end: datetime) -> list[tuple[str, str]]:
    """官方单次查询间隔 ≤7 天；按 7 天一段拆分，游戏日边界为凌晨 5 点。
    最后一段结束时间封顶到 `end`（官方要求结束时间必须早于当前时间）。"""
    segments: list[tuple[str, str]] = []
    cursor = start
    end_date = end.date()
    while cursor <= end_date:
        seg_end_date = min(cursor + timedelta(days=6), end_date)
        if seg_end_date == end_date:
            seg_end_ts = end.strftime("%Y-%m-%d %H:%M:%S")
        else:
            seg_end_ts = f"{seg_end_date} 23:59:59"
        segments.append((f"{cursor} 05:00:00", seg_end_ts))
        cursor = seg_end_date + timedelta(days=1)
    return segments


def _record_name(record: dict[str, Any]) -> str:
    for key in ("scratchCardId", "activityName", "activity", "name", "itemName", "description", "title", "content"):
        value = record.get(key)
        if value:
            return str(value)
    return ""


def _record_award(record: dict[str, Any]) -> int:
    award_text = ""
    for key in ("award", "awardText", "totalReward", "amount", "itemAmount", "gain", "reward"):
        value = record.get(key)
        if value not in (None, ""):
            award_text = str(value)
            break
    if not award_text:
        return 0
    match = _FANGSI_RE.search(award_text)
    if match:
        value = int(match.group(1).replace(",", ""))
    else:
        match = _NUMBER_RE.search(award_text)
        value = int(match.group(1).replace(",", "")) if match else 0
    if "未中奖" in award_text or "0方斯" in award_text or award_text.strip() == "0":
        return 0
    return value


def _game_day(log_time: str) -> str:
    """游戏日以凌晨 5 点为界：05:00 前归前一天。"""
    try:
        moment = datetime.strptime(log_time[:19], "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return (log_time or "")[:10]
    if moment.hour < 5:
        moment -= timedelta(days=1)
    return moment.strftime("%Y-%m-%d")


def build_scratch_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    total_cost = 0
    total_gain = 0
    win_count = 0
    max_award = 0
    big_count = 0
    big_gain = 0
    card_kinds: set[str] = set()
    day_net: dict[str, int] = {}
    max_consecutive_losses = 0
    consecutive = 0

    for record in records:
        name = _record_name(record)
        if name:
            card_kinds.add(name)
        cost = SCRATCH_CARD_COSTS.get(name, DEFAULT_COST)
        award = _record_award(record)
        total_cost += cost
        total_gain += award
        if award > 0:
            win_count += 1
            consecutive = 0
        else:
            consecutive += 1
            max_consecutive_losses = max(max_consecutive_losses, consecutive)
        max_award = max(max_award, award)
        if award >= BIG_AWARD:
            big_count += 1
            big_gain += award
        day = _game_day(str(record.get("logTime") or record.get("time") or ""))
        day_net[day] = day_net.get(day, 0) + award - cost

    total = len(records)
    empty_count = total - win_count
    best_day = max(day_net.items(), key=lambda item: item[1]) if day_net else ("", 0)
    worst_day = min(day_net.items(), key=lambda item: item[1]) if day_net else ("", 0)
    recovery = total_gain / total_cost * 100 if total_cost else 0.0

    return {
        "total_cost": total_cost,
        "total_gain": total_gain,
        "net": total_gain - total_cost,
        "recovery": recovery,
        "profit_rate": recovery - 100,
        "flow": total_cost + total_gain,
        "total": total,
        "win_count": win_count,
        "empty_count": empty_count,
        "avg_award": total_gain / total if total else 0,
        "max_award": max_award,
        "big_count": big_count,
        "big_ratio": big_gain / total_gain * 100 if total_gain else 0.0,
        "hit_rate": win_count / total * 100 if total else 0.0,
        "card_kinds": len(card_kinds),
        "active_days": len(day_net),
        "max_consecutive_losses": max_consecutive_losses,
        "best_day": best_day,
        "worst_day": worst_day,
        "pages": (total + 99) // 100,
    }


async def bind_scratch_cookie(bot: Bot, ev: Event) -> None:
    cookie = ev.text.strip()
    lowered = cookie.lower()
    if not cookie or ("wmlogon" not in lowered and "session" not in lowered):
        return await send_nte_notify(bot, ev, ScratchMsg.usage())
    if "wmlogon=" in lowered and "session=" not in lowered:
        try:
            match = re.search(r"wmlogon=([^;\s]+)", cookie, re.I)
            if match:
                cookie = await _kf_session_cookie(match.group(1))
        except ScratchLoginError as error:
            return await send_nte_notify(bot, ev, ScratchMsg.cookie_expired())
    changed = await NTEUser.bind_wm_cookie(ev.user_id, ev.bot_id, cookie)
    if not changed:
        return await send_nte_notify(bot, ev, ScratchMsg.not_logged_in())
    logger.info(f"[{TAG}] user_id={ev.user_id} 绑定 wmLogon Cookie")
    await send_nte_notify(bot, ev, ScratchMsg.BIND_OK)


async def unbind_scratch_cookie(bot: Bot, ev: Event) -> None:
    changed = await NTEUser.unbind_wm_cookie(ev.user_id, ev.bot_id)
    if not changed:
        return await send_nte_notify(bot, ev, ScratchMsg.UNBIND_EMPTY)
    logger.info(f"[{TAG}] user_id={ev.user_id} 解绑 wmLogon Cookie")
    await send_nte_notify(bot, ev, ScratchMsg.UNBIND_OK)


async def run_scratch_query(bot: Bot, ev: Event, text: str) -> None:
    """刮刮乐查询：官方要求滑块验证，统一走网页滑块流程，战报自动发回 QQ。

    第一次使用（未绑定完美世界账号）时直接发登录链接引导，不依赖塔吉多登录。
    """
    target = await resolve_at_target(bot, ev)
    if target is None:
        return
    user = await NTEUser.get_scratch_user(target.user_id, ev.bot_id)
    if user is None:
        if target.is_other:
            return await send_nte_notify(bot, ev, ScratchMsg.other_not_bound())
        return await send_scratch_login(bot, ev)
    ok, limit_msg = _check_query_limit(target.user_id)
    if not ok:
        return await send_nte_notify(bot, ev, limit_msg)

    days = _parse_days(text)
    auth = begin_scratch_login(
        ev.user_id,
        ev.bot_id,
        bot_self_id=ev.bot_self_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
        target_user_id=target.user_id,
    )
    url = f"{await scratch_login_page_url()}/nte/scratch/query/{auth}"
    await bot.send(
        f"[异环] 刮刮乐战报 · {user.role_name} 近{days}天\n{url}\n"
        f"链接{SCRATCH_LOGIN_TTL // 60}分钟内有效，滑完自动出卡",
        at_sender=bool(ev.group_id),
    )


async def send_scratch_login(bot: Bot, ev: Event) -> None:
    """网页登录：机器人发链接，用户浏览器正常登录后自动绑定。"""
    auth = begin_scratch_login(
        ev.user_id,
        ev.bot_id,
        bot_self_id=ev.bot_self_id,
        user_type=ev.user_type,
        group_id=ev.group_id,
    )
    url = f"{await scratch_login_page_url()}/nte/scratch/{auth}"
    lines = [
        "[异环] 刮刮乐登录",
        f" {url}",
        f"链接{SCRATCH_LOGIN_TTL // 60}分钟内有效，登录后发【刮刮乐】直接查询",
    ]
    await bot.send("\n".join(lines), at_sender=bool(ev.group_id))


async def run_scratch_rank(bot: Bot, ev: Event) -> None:
    """群内刮刮乐亏损排行：只统计塔吉多已登录账号（有塔吉多才生成排名）。"""
    if not ev.group_id:
        return await send_nte_notify(bot, ev, ScratchMsg.RANK_GROUP_ONLY)
    members = await NTEGroupMember.list_members(ev.group_id, ev.bot_id)
    if not members:
        return await send_nte_notify(bot, ev, ScratchMsg.RANK_EMPTY)
    rows = await NTEUser.list_scratch_stats_by_uids(ev.bot_id, [m.uid for m in members])
    seen: set[str] = set()
    deduped = []
    for row in rows:
        # 仅统计塔吉多已登录的账号（cookie/access_token 非空）
        if not (row.cookie or row.access_token):
            continue
        if row.uid in seen:
            continue
        seen.add(row.uid)
        deduped.append(row)
    if not deduped:
        return await send_nte_notify(bot, ev, ScratchMsg.RANK_EMPTY)
    entries = [
        {
            "role_name": row.role_name or "未知",
            "uid": row.uid,
            "net": int(row.wm_net or 0),
            "cost": int(row.wm_cost or 0),
            "gain": int(row.wm_gain or 0),
            "updated": row.wm_updated_at or "",
        }
        for row in deduped
    ]
    entries.sort(key=lambda item: item["net"])
    for index, item in enumerate(entries, 1):
        item["rank"] = index
    img = await draw_scratch_rank_img(ev, entries)
    await bot.send(img)


async def _do_query(bot: Bot, ev: Event, text: str, target: AtTarget) -> None:
    user = await NTEUser.get_scratch_user(target.user_id, ev.bot_id)
    if user is None:
        if target.is_other:
            return await send_nte_notify(bot, ev, ScratchMsg.other_not_bound())
        return await send_nte_notify(bot, ev, ScratchMsg.not_bound())
    if not user.wm_cookie:
        return await send_nte_notify(bot, ev, ScratchMsg.not_bound(is_other=target.is_other))

    days = _parse_days(text)
    cache_key = f"scratch:{target.user_id}:{user.uid}:{days}"
    cached = RESULT_CACHE.get(cache_key)
    if cached is not None:
        return await bot.send(cached)

    end = datetime.now() - timedelta(seconds=60)
    start = (end - timedelta(days=days - 1)).date()
    segments = _split_segments(start, end)
    try:
        records = await _fetch_records(user.wm_cookie, user.uid, segments)
    except WanmeiCaptchaError as err:
        return await send_nte_notify(bot, ev, ScratchMsg.captcha_required(str(err)))
    except WanmeiError as err:
        if _cookie_invalid(err) and "session=" not in user.wm_cookie.lower():
            # 缺少 SESSION 时尝试从客服页补一次后重试
            try:
                enriched = await _kf_session_cookie(user.wm_cookie)
            except ScratchLoginError:
                enriched = ""
            if enriched and enriched != user.wm_cookie:
                await NTEUser.bind_wm_cookie(target.user_id, ev.bot_id, enriched)
                user.wm_cookie = enriched
                try:
                    records = await _fetch_records(enriched, user.uid, segments)
                except WanmeiError as retry_err:
                    if _cookie_invalid(retry_err):
                        return await send_nte_notify(
                            bot, ev, ScratchMsg.cookie_expired(is_other=target.is_other)
                        )
                    logger.warning(f"[{TAG}] 查询失败 user_id={target.user_id}: {retry_err.message}")
                    return await send_nte_notify(bot, ev, ScratchMsg.FAILED)
                except WanmeiCaptchaError as captcha_err:
                    return await send_nte_notify(bot, ev, ScratchMsg.captcha_required(str(captcha_err)))
            else:
                if _cookie_invalid(err):
                    return await send_nte_notify(bot, ev, ScratchMsg.cookie_expired(is_other=target.is_other))
                return await send_nte_notify(bot, ev, ScratchMsg.FAILED)
        else:
            logger.warning(f"[{TAG}] 查询失败 user_id={target.user_id}: {err.message}")
            return await send_nte_notify(bot, ev, ScratchMsg.FAILED)

    if not records:
        return await send_nte_notify(bot, ev, ScratchMsg.EMPTY)

    stats = build_scratch_stats(records)
    await NTEUser.save_scratch_stats(
        target.user_id,
        ev.bot_id,
        user.uid,
        stats["net"],
        stats["total_cost"],
        stats["total_gain"],
    )
    img = await draw_scratch_card_img(ev, user.role_name, user.uid, start, end, days, stats, records)
    RESULT_CACHE.set(cache_key, img)
    await bot.send(img)


async def _fetch_records(
    cookie: str,
    role_id: str,
    segments: list[tuple[str, str]],
    *,
    cap_ticket: str = "",
    sec_code: str = "",
) -> list[dict[str, Any]]:
    """分段拉取记录；各段并发执行（限 4 路）以缩短 60 天全量查询耗时。
    官方接口对「该区间无记录」返回错误而非空列表，空段视为 0 条继续。
    """
    client = WanmeiScratchClient(cookie)
    semaphore = asyncio.Semaphore(4)

    async def fetch_segment(seg_start: str, seg_end: str) -> list[dict[str, Any]]:
        async with semaphore:
            seg_records: list[dict[str, Any]] = []
            page_no = 1
            seg_fetched = 0
            while True:
                try:
                    data = await client.search(
                        role_id,
                        seg_start,
                        seg_end,
                        page_no=page_no,
                        cap_ticket=cap_ticket,
                        sec_code=sec_code,
                    )
                except WanmeiError as err:
                    # 官方接口对「该区间无记录」返回错误而非空列表；
                    # 分段查询时应视为空段继续查后续区间，不能中断整个查询。
                    if "没有搜索到" in err.message or "暂无" in err.message:
                        logger.debug(f"[{TAG}] 分段 {seg_start} ~ {seg_end} 无记录，继续下一段")
                        break
                    raise
                result = data.get("result") or []
                seg_records.extend(result)
                seg_fetched += len(result)
                total = int(data.get("total") or 0)
                if not result or total <= seg_fetched or page_no >= 10:
                    break
                page_no += 1
            return seg_records

    results = await asyncio.gather(*(fetch_segment(s, e) for s, e in segments))
    records: list[dict[str, Any]] = []
    for seg_records in results:
        records.extend(seg_records)
    return records


async def build_scratch_report(
    user: NTEUser,
    days: int,
    *,
    cap_ticket: str = "",
    sec_code: str = "",
) -> tuple[bytes | None, str]:
    """执行查询并渲染战报，返回 (图片 bytes 或 None, 错误文案或空串)。"""
    end = datetime.now() - timedelta(seconds=60)
    start = (end - timedelta(days=days - 1)).date()
    cache_key = f"scratch:{user.user_id}:{user.uid}:{days}"
    cached = RESULT_CACHE.get(cache_key)
    if cached is not None:
        return cached, ""

    segments = _split_segments(start, end)
    try:
        records = await _fetch_records(
            user.wm_cookie,
            user.uid,
            segments,
            cap_ticket=cap_ticket,
            sec_code=sec_code,
        )
    except WanmeiCaptchaError as err:
        return None, ScratchMsg.captcha_required(str(err))
    except WanmeiError as err:
        if "没有搜索到" in err.message or "暂无" in err.message:
            return None, ScratchMsg.EMPTY
        if _cookie_invalid(err):
            return None, ScratchMsg.cookie_expired()
        logger.warning(f"[{TAG}] 查询失败 user_id={user.user_id}: {err.message}")
        return None, ScratchMsg.FAILED

    if not records:
        return None, ScratchMsg.EMPTY

    stats = build_scratch_stats(records)
    await NTEUser.save_scratch_stats(
        user.user_id,
        user.bot_id,
        user.uid,
        stats["net"],
        stats["total_cost"],
        stats["total_gain"],
    )
    ev = Event(
        bot_id=user.bot_id,
        user_id=user.user_id,
        bot_self_id=user.bot_id,
        user_type="direct",
        group_id=None,
        sender={},
    )
    img = await draw_scratch_card_img(ev, user.role_name, user.uid, start, end, days, stats, records)
    RESULT_CACHE.set(cache_key, img)
    return img, ""


def _cookie_invalid(error: WanmeiError) -> bool:
    raw = error.raw
    if isinstance(raw, dict):
        status = raw.get("status_code")
        if status in (301, 302, 303, 307, 308):
            return True
    message = error.message
    return "Cookie" in message or "登录" in message or "失效" in message
