from __future__ import annotations

import asyncio
import re
from datetime import datetime
from typing import Any

from app.repositories import (
    list_tip_first_seen,
    list_tips,
    record_site_scrape,
    replace_site_tips,
    tip_first_seen_key,
)
from app.services.zodiac import ZODIAC_ORDER
from app.sites import TipSite, all_tip_fetch_urls, enabled_tip_sites

# 单站抓取上限，避免某一站线路页把整次开奖前刷新拖死
_SITE_SCRAPE_TIMEOUT_SEC = 75
# 启用站大约 5 个；并行上限 5，整轮 tip 墙钟时间约等于最慢那一站（≤75s）
_TIP_SCRAPE_CONCURRENCY = 5
# 连接被对端掐断时短等再试一次，仍算在单站 75s 预算里
_CONNECTION_RETRY_SLEEP_SEC = 3.0
_CONNECTION_ERROR_MARKS = (
    "err_connection_closed",
    "connection_closed",
    "connection closed",
    "connection reset",
    "connection aborted",
    "econnreset",
    "forcibly closed",
    "强制关闭",
    "强迫关闭",
    "broken pipe",
    "winerror 10054",
    "10054",
)

FAIL_REASON_LABEL = {
    "timeout": "超时",
    "route_page": "线路页",
    "no_period": "名单未出",  # 当期期号尚未出现，常见于晚出，不按坏站处理
    "no_list": "没有名单",
    "connection_closed": "连接断开",
    "fetch_error": "抓取失败",
}
_ROUTE_MARKS = ("点击进入", "进入网站", "立即进入", "线路选择", "选择线路")

_XIAO_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
_ZODIAC_CHARS = set("鼠牛虎兔龙蛇马羊猴鸡狗猪")
_LABEL_RE = re.compile(r"([一二三四五六七八九])肖")
# 明文绝杀：绝杀一肖：猴 / 综合绝杀：羊 / 表格式「绝杀\t鸡肖」
_KILL_LABEL_RE = re.compile(
    r"(?:绝杀一肖|综合绝杀)\s*[:：]\s*([鼠牛虎兔龙蛇马羊猴鸡狗猪])"
)
_KILL_TABLE_RE = re.compile(
    r"绝杀\s*([鼠牛虎兔龙蛇马羊猴鸡狗猪])肖?(?=[.\s开]|$)"
)


def _chunks_for_period(text: str, period: int) -> list[str]:
    pattern = re.compile(rf"{period}期.*?(?=\d{{1,4}}期|$)", re.S)
    return [m.group(0).strip() for m in pattern.finditer(text) if m.group(0).strip()]


def _scope_for_period(text: str, period: int) -> str:
    """只看当期期号后面的段落，避免把别的期或整页广告算进来。"""
    chunks = _chunks_for_period(text, period)
    if chunks:
        return "\n".join(chunks[:12])
    idx = text.find(f"{period}期")
    if idx < 0:
        return ""
    return text[idx : idx + 4000]


def _is_sep(ch: str) -> bool:
    if ch.isspace() or ch.isascii():
        return True
    if ch in "〖〗【】[]()（）:：、，,。·.✔㊣+*/|_-—~～!！?？\"'「」『』《》<>":
        return True
    if "\u2460" <= ch <= "\u2473" or "\u2776" <= ch <= "\u277f":
        return True
    return False


def _read_zodiac_run(text: str, start: int) -> list[str]:
    """从肖标签后读取连续生肖。中间只允许标点和「一码」「独肖」，广告词会把名单截断。"""
    i = start
    n = len(text)
    zodiacs: list[str] = []
    while i < n and not zodiacs:
        if text.startswith("一码", i) or text.startswith("独肖", i):
            i += 2
            continue
        ch = text[i]
        if ch in _ZODIAC_CHARS:
            break
        if _is_sep(ch):
            i += 1
            continue
        return []
    while i < n:
        ch = text[i]
        if ch in _ZODIAC_CHARS:
            zodiacs.append(ch)
            i += 1
            continue
        if not _is_sep(ch):
            break
        j = i + 1
        while j < n and _is_sep(text[j]):
            j += 1
        if j < n and text[j] in _ZODIAC_CHARS:
            i = j
            continue
        break
    return zodiacs


def parse_xiao_runs(text: str) -> list[dict[str, Any]]:
    """只保留「N肖」后面个数正好相等的生肖串。"""
    out: list[dict[str, Any]] = []
    seen: set[tuple[int, tuple[str, ...]]] = set()
    for m in _LABEL_RE.finditer(text or ""):
        count = _XIAO_NUM[m.group(1)]
        zodiacs = _read_zodiac_run(text, m.end())
        if len(zodiacs) != count or len(set(zodiacs)) != count:
            continue
        key = (count, tuple(zodiacs))
        if key in seen:
            continue
        seen.add(key)
        label = f"{m.group(1)}肖"
        out.append(
            {
                "strategy": "xiao_line",
                "raw": text[m.start() : m.end() + 40][:500],
                "zodiacs": zodiacs,
                "tip_type": label,
                "count": count,
            }
        )
    return out


def _is_prefix(short: tuple[str, ...], long: tuple[str, ...]) -> bool:
    return len(short) < len(long) and long[: len(short)] == short


def scope_for_xiao(count: int) -> str:
    return "te_ma" if count <= 3 else "bao_xiao"


def select_ladder_tips(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """同一条由短到长的阶梯只留一档：特码留最短，包肖留最长。"""
    uniq: dict[tuple[str, ...], dict[str, Any]] = {}
    for item in items:
        zodiacs = tuple(item.get("zodiacs") or [])
        count = int(item.get("count") or len(zodiacs))
        if not zodiacs or count != len(zodiacs):
            continue
        uniq[zodiacs] = {**item, "zodiacs": list(zodiacs), "count": count}
    rows = list(uniq.values())
    parent = list(range(len(rows)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    seqs = [tuple(row["zodiacs"]) for row in rows]
    for i, left in enumerate(seqs):
        for j in range(i + 1, len(seqs)):
            right = seqs[j]
            if _is_prefix(left, right) or _is_prefix(right, left):
                union(i, j)

    groups: dict[int, list[dict[str, Any]]] = {}
    for i, row in enumerate(rows):
        groups.setdefault(find(i), []).append(row)

    kept: list[dict[str, Any]] = []
    for group in groups.values():
        short = [row for row in group if row["count"] <= 3]
        long = [row for row in group if row["count"] >= 4]
        if short:
            kept.append(min(short, key=lambda row: row["count"]))
        if long:
            kept.append(max(long, key=lambda row: row["count"]))
    for row in kept:
        row["play_scope"] = scope_for_xiao(int(row["count"]))
    return kept


def classify_empty_page(text: str, period: int) -> str:
    """页面打开了，但没有可用名单。线路页、找不到期号、有期号但抽不出肖，分开记。"""
    body = text or ""
    if f"{period}期" not in body:
        if any(mark in body for mark in _ROUTE_MARKS):
            return "route_page"
        return "no_period"
    return "no_list"


def classify_fetch_error(exc: BaseException) -> str:
    blob = f"{type(exc).__name__} {exc}".lower()
    if "timeout" in blob or "timed out" in blob:
        return "timeout"
    if any(mark in blob for mark in _CONNECTION_ERROR_MARKS):
        return "connection_closed"
    return "fetch_error"


def is_connection_fetch_error(exc: BaseException) -> bool:
    return classify_fetch_error(exc) == "connection_closed"


def parse_kill_xiao(text: str) -> list[dict[str, Any]]:
    """只认明文绝杀单肖，不解析笑话/玄机图。tip_type=绝杀，play_scope=te_ma。"""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    body = text or ""
    for cre in (_KILL_LABEL_RE, _KILL_TABLE_RE):
        for m in cre.finditer(body):
            zodiac = m.group(1)
            if zodiac in seen:
                continue
            seen.add(zodiac)
            raw = body[m.start() : m.end() + 8][:200]
            out.append(
                {
                    "strategy": "kill_line",
                    "raw": raw,
                    "zodiacs": [zodiac],
                    "tip_type": "绝杀",
                    "count": 1,
                    "play_scope": "te_ma",
                }
            )
    return out


def _period_kill_scope(text: str, period: int) -> str:
    """绝杀对照表常在页尾，不截前 12 段，把当期全部块拼起来。"""
    chunks = _chunks_for_period(text, period)
    if chunks:
        return "\n".join(chunks)
    return _scope_for_period(text, period)


def extract_candidates(text: str, period: int) -> list[dict[str, Any]]:
    """当期段落：包肖/短名单阶梯 + 明文绝杀（特码旁路，不进包肖分）。"""
    scope = _scope_for_period(text, period)
    if not scope:
        return []
    ladder = select_ladder_tips(parse_xiao_runs(scope))
    kills = parse_kill_xiao(_period_kill_scope(text, period))
    return ladder + kills


def extract_kill_only(text: str, period: int) -> list[dict[str, Any]]:
    """特码专用页：只抽绝杀，不跑包肖阶梯。"""
    scope = _period_kill_scope(text, period) or (text or "")
    return parse_kill_xiao(scope)


def play_scope_for_tip(raw: str, tip_type: str | None, zodiacs: list[str]) -> str | None:
    """一肖到三肖归特码，四肖到九肖归包肖。绝杀固定特码。个数对不上的不参与。"""
    if (tip_type or "") == "绝杀":
        return "te_ma"
    parsed = parse_xiao_runs(raw or "")
    if len(parsed) == 1:
        return scope_for_xiao(int(parsed[0]["count"]))
    label = tip_type or ""
    count = _XIAO_NUM.get(label[:1])
    if count and len(zodiacs or []) == count:
        return scope_for_xiao(count)
    return None


def collapse_site_tips(tips: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按站点把已入库原文重新收成阶梯各一档；绝杀明文单独保留。"""
    grouped: dict[str, list[dict[str, Any]]] = {}
    kills: list[dict[str, Any]] = []
    for tip in tips:
        site = str(tip.get("site_code") or "")
        tip_type = str(tip.get("tip_type") or "")
        zodiacs = tip.get("parsed_zodiacs") or tip.get("zodiacs") or []
        if isinstance(zodiacs, str):
            try:
                import json

                zodiacs = json.loads(zodiacs)
            except Exception:
                zodiacs = []
        if tip_type == "绝杀" or tip.get("strategy") == "kill_line":
            zs = [z for z in list(zodiacs) if z in _ZODIAC_CHARS]
            if len(zs) == 1:
                kills.append(
                    {
                        "site_code": site,
                        "zodiacs": zs,
                        "tip_type": "绝杀",
                        "count": 1,
                        "play_scope": "te_ma",
                        "strategy": "kill_line",
                        "raw": tip.get("raw_text") or tip.get("raw") or "",
                    }
                )
            continue
        raw = str(tip.get("raw_text") or tip.get("raw") or "")
        grouped.setdefault(site, []).extend(parse_xiao_runs(raw))
        # 原文里若仍有绝杀明文，一并收出
        for item in parse_kill_xiao(raw):
            kills.append({**item, "site_code": site})
    kept: list[dict[str, Any]] = []
    for site, items in grouped.items():
        for item in select_ladder_tips(items):
            kept.append({**item, "site_code": site})
    seen_kill: set[tuple[str, str]] = set()
    for item in kills:
        key = (str(item.get("site_code") or ""), (item.get("zodiacs") or [""])[0])
        if key in seen_kill or not key[1]:
            continue
        seen_kill.add(key)
        kept.append(item)
    return kept


def contributing_tips(tips: list[dict[str, Any]], play_type: str) -> list[dict[str, Any]]:
    """打分用的资料：各站阶梯收档后，只留该玩法的那一档。绝杀永不进包肖。"""
    out = []
    for tip in collapse_site_tips(tips):
        if tip.get("tip_type") == "绝杀" and play_type == "bao_xiao":
            continue
        if tip.get("play_scope") == play_type:
            out.append(tip)
    return out


def _merge_tip_rows(
    base: list[dict[str, Any]], extra: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """合并绝杀等到已有行；同站同玩法同 tip_type 同名单不重复。"""
    keys = {
        (
            str(r.get("play_scope") or ""),
            str(r.get("tip_type") or ""),
            tuple(r.get("parsed_zodiacs") or r.get("zodiacs") or []),
        )
        for r in base
    }
    out = list(base)
    for row in extra:
        key = (
            str(row.get("play_scope") or ""),
            str(row.get("tip_type") or ""),
            tuple(row.get("parsed_zodiacs") or row.get("zodiacs") or []),
        )
        if key in keys:
            continue
        keys.add(key)
        out.append(row)
    return out


def _rows_from_candidates(
    site_code: str,
    url: str,
    candidates: list[dict[str, Any]],
    prior_seen: dict[tuple[str, str, str, tuple[str, ...]], datetime] | None = None,
) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    strategies: list[str] = []
    picked: list[dict[str, Any]] = []
    per_scope = {"bao_xiao": 0, "te_ma": 0}
    for item in candidates:
        zodiacs = item.get("zodiacs") or []
        if not zodiacs:
            continue
        scope = item.get("play_scope") or play_scope_for_tip(
            str(item.get("raw") or ""), item.get("tip_type"), zodiacs
        )
        if scope not in per_scope:
            continue
        # 绝杀与普通短名单可并存，不占 te_ma 阶梯配额
        if item.get("tip_type") == "绝杀":
            picked.append({**item, "play_scope": "te_ma"})
            continue
        if per_scope[scope] >= 8:
            continue
        per_scope[scope] += 1
        picked.append({**item, "play_scope": scope})
    for item in picked:
        zodiacs = item.get("zodiacs") or []
        strategy = str(item.get("strategy") or "unknown")
        raw = f"[{strategy}] {item.get('raw') or ''}"
        scope = item.get("play_scope")
        tip_type = item.get("tip_type")
        seen_key = tip_first_seen_key(site_code, scope, tip_type, zodiacs)
        rows.append(
            {
                "page_url": url,
                "raw_text": raw[:5000],
                "parsed_zodiacs": zodiacs,
                "tip_type": tip_type,
                "play_scope": scope,
                "first_seen_at": (prior_seen or {}).get(seen_key),
            }
        )
        if strategy not in strategies:
            strategies.append(strategy)
    return rows, strategies


async def _fetch_text(url: str, prefer_frames: bool) -> str:
    from app.scrapers.browser import fetch_page_text

    if prefer_frames:
        text = await fetch_page_text(url, wait_ms=3500, include_frames=True)
        if len(text.strip()) < 40:
            text = await fetch_page_text(url, wait_ms=2500, include_frames=False)
        return text
    text = await fetch_page_text(url, wait_ms=2500, include_frames=False)
    if "七肖" not in text and "一肖" not in text and "九肖" not in text:
        text = await fetch_page_text(url, wait_ms=3500, include_frames=True)
    return text


async def _fetch_text_retry_connection(url: str, prefer_frames: bool) -> tuple[str, bool]:
    """普通抓取；若连接被掐断，短间隔后再试一次。返回 (正文, 是否已重试)。"""
    try:
        return await _fetch_text(url, prefer_frames), False
    except Exception as first:
        if not is_connection_fetch_error(first):
            raise
        await asyncio.sleep(_CONNECTION_RETRY_SLEEP_SEC)
        try:
            return await _fetch_text(url, prefer_frames), True
        except Exception as second:
            setattr(second, "_tip_connection_retried", True)
            raise


async def scrape_tip_site(
    period: int,
    site: TipSite,
    prior_seen: dict[tuple[str, str, str, tuple[str, ...]], datetime] | None = None,
) -> dict[str, Any]:
    """只抓不写库。抓到的名单放在 rows 里，由 sync_tips 统一替换。"""
    rows: list[dict[str, Any]] = []
    used: list[str] = []
    strategies_used: list[str] = []
    empty_reason: str | None = None
    error_reason: str | None = None
    error_detail = ""
    prefer = site.prefer_frames or "dinggeshui" in site.code

    urls = all_tip_fetch_urls(site)
    tried_extra = False
    fetched_urls: set[str] = set()

    i = 0
    while i < len(urls):
        url = urls[i]
        i += 1
        try:
            text, connection_retried = await _fetch_text_retry_connection(url, prefer)
            fetched_urls.add(url)
            candidates = extract_candidates(text, period)
            found, st = _rows_from_candidates(site.code, url, candidates, prior_seen)
            used.append(f"{url}#retried=1" if connection_retried else url)
            for s in st:
                if s not in strategies_used:
                    strategies_used.append(s)
            if found:
                rows = found
                empty_reason = None
                break
            empty_reason = classify_empty_page(text, period)
            # 主 URL 抽不到：按站点上限翻资料链；0 表示不翻（慢站保超时预算）
            if not tried_extra and site.max_extra_links > 0:
                tried_extra = True
                from app.scrapers.browser import discover_tip_links

                extras = await discover_tip_links(url, limit=site.max_extra_links)
                for e in extras:
                    if e not in urls:
                        urls.append(e)
        except Exception as exc:
            error_reason = classify_fetch_error(exc)
            retried = bool(getattr(exc, "_tip_connection_retried", False))
            suffix = "; retried=1" if retried else ""
            error_detail = f"{type(exc).__name__}: {exc}{suffix}"
            used.append(f"{url}#err:{error_detail}")

    # 特码绝杀专用页：只抽绝杀明文，合并进 rows，不改已有包肖阶梯
    kill_fail_detail = ""
    for url in site.tema_tip_urls:
        if url in fetched_urls:
            continue
        try:
            text, connection_retried = await _fetch_text_retry_connection(url, prefer)
            fetched_urls.add(url)
            kills = extract_kill_only(text, period)
            found, st = _rows_from_candidates(site.code, url, kills, prior_seen)
            used.append(
                (f"{url}#tema#retried=1" if connection_retried else f"{url}#tema")
            )
            for s in st:
                if s not in strategies_used:
                    strategies_used.append(s)
            if found:
                rows = _merge_tip_rows(rows, found)
                empty_reason = None
                error_reason = None
            elif not rows:
                empty_reason = classify_empty_page(text, period)
                kill_fail_detail = empty_reason or "no_kill"
        except Exception as exc:
            reason = classify_fetch_error(exc)
            retried = bool(getattr(exc, "_tip_connection_retried", False))
            suffix = "; retried=1" if retried else ""
            detail = f"{type(exc).__name__}: {exc}{suffix}"
            used.append(f"{url}#tema#err:{detail}")
            if not rows:
                error_reason = reason
                kill_fail_detail = detail

    if rows:
        fail_reason = None
        error_detail = ""
    elif empty_reason:
        fail_reason = empty_reason
        error_detail = kill_fail_detail or error_detail
    else:
        fail_reason = error_reason or "fetch_error"
        if kill_fail_detail and not error_detail:
            error_detail = kill_fail_detail
    return {
        "site": site.code,
        "name": site.name,
        "saved": len(rows),
        "rows": rows,
        "urls": used,
        "strategies": strategies_used,
        "note": site.note,
        "fail_reason": fail_reason,
        "fail_detail": "" if rows else (error_detail if fail_reason == error_reason else error_detail),
        "kill_tips": sum(1 for r in rows if r.get("tip_type") == "绝杀"),
    }


async def _scrape_site_bounded(
    period: int,
    site: TipSite,
    prior_seen: dict[tuple[str, str, str, tuple[str, ...]], datetime],
    sem: asyncio.Semaphore,
) -> dict[str, Any]:
    """单站限时抓取；并发由 semaphore 卡住上限。"""
    async with sem:
        try:
            return await asyncio.wait_for(
                scrape_tip_site(period, site, prior_seen),
                timeout=_SITE_SCRAPE_TIMEOUT_SEC,
            )
        except asyncio.TimeoutError:
            return {
                "site": site.code,
                "name": site.name,
                "saved": 0,
                "rows": [],
                "urls": [],
                "strategies": [],
                "note": site.note,
                "fail_reason": "timeout",
                "fail_detail": f"单站超过 {_SITE_SCRAPE_TIMEOUT_SEC}s",
            }


async def sync_tips(period: int) -> dict[str, Any]:
    """多站并行抓完后再统一替换。没抓到的站保留上次名单，避免一次超时让分数跳动。

    并发上限 `_TIP_SCRAPE_CONCURRENCY`（默认 5）；单站仍 75s。
    开奖前 21:00–21:20 再点「刷新分析」可补齐晚出名单。
    """
    prior_seen = list_tip_first_seen(period)
    prior_sites = {str(tip.get("site_code") or "") for tip in list_tips(period)}
    sites = enabled_tip_sites()
    sem = asyncio.Semaphore(_TIP_SCRAPE_CONCURRENCY)
    scraped = await asyncio.gather(
        *[_scrape_site_bounded(period, site, prior_seen, sem) for site in sites]
    )

    results: dict[str, Any] = {
        "period": period,
        "sites": [],
        "concurrency": _TIP_SCRAPE_CONCURRENCY,
        "site_timeout_sec": _SITE_SCRAPE_TIMEOUT_SEC,
    }
    fresh: dict[str, list[dict[str, Any]]] = {}
    for item in scraped:
        rows = item.pop("rows")
        code = str(item["site"])
        had_prior = code in prior_sites
        if rows:
            fresh[code] = rows
            status = record_site_scrape(code, ok=True, period=period)
        else:
            status = record_site_scrape(
                code,
                ok=False,
                period=period,
                reason=item.get("fail_reason"),
                detail=item.get("fail_detail") or item.get("fail_reason"),
                had_prior_tips=had_prior,
            )
        item["fail_streak"] = status["fail_streak"]
        item["alert"] = status["alert"]
        item["reuse"] = status.get("reuse")
        item["counted"] = status.get("counted")
        results["sites"].append(item)
        results[code] = item
    replace_site_tips(period, fresh)
    results["saved_total"] = sum(len(rows) for rows in fresh.values())
    results["kept_sites"] = [s["site"] for s in results["sites"] if not s["saved"]]
    results["alerts"] = [
        {
            "site": item["site"],
            "name": item.get("name") or item["site"],
            "fail_streak": item.get("fail_streak"),
            "fail_reason": item.get("fail_reason"),
            "fail_label": FAIL_REASON_LABEL.get(
                item.get("fail_reason") or "", item.get("fail_reason")
            ),
            "reuse": item.get("reuse"),
        }
        for item in results["sites"]
        if item.get("alert")
    ]
    return results


def tip_scores_for_period(
    period: int,
    tips: list[dict[str, Any]],
    *,
    play_type: str = "bao_xiao",
    site_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """阶梯收档后的资料分。每个生肖只分到该档名单的一份，不再按肖数再打一层折。"""
    weights = site_weights or {}
    scores = {z: 0.0 for z in ZODIAC_ORDER}
    for tip in contributing_tips(tips, play_type):
        if tip.get("tip_type") == "绝杀" and play_type == "bao_xiao":
            continue
        zodiacs = list(tip.get("zodiacs") or [])
        if not zodiacs:
            continue
        w = float(weights.get(str(tip.get("site_code") or ""), 1.0))
        if w <= 0:
            continue
        focus = 1.0 / len(zodiacs)
        for zodiac in zodiacs:
            if zodiac in scores:
                scores[zodiac] += w * focus
    return scores


def primary_tip_for_site(
    tips: list[dict[str, Any]], *, play_type: str | None = None
) -> dict[str, Any] | None:
    """每站取收档后最聚焦的一条作为对账主推。"""
    rows = collapse_site_tips(tips)
    if play_type:
        rows = [tip for tip in rows if tip.get("play_scope") == play_type]
    if not rows:
        return None
    picked = sorted(rows, key=lambda tip: (int(tip.get("count") or 99), tip.get("tip_type") or ""))[0]
    zodiacs = list(picked.get("zodiacs") or [])
    return {**picked, "parsed_zodiacs": zodiacs, "zodiacs": zodiacs}
