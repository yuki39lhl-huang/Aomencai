"""Windows + uvicorn 下 async Playwright 用同步 API + 线程。"""
from __future__ import annotations

import asyncio
import re
from urllib.parse import urljoin


TIP_LINK_RE = re.compile(r"(肖|特码|平特|开奖|资料|心水|推荐)")


def fetch_page_text_sync(url: str, *, wait_ms: int = 3000, include_frames: bool = False) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(wait_ms)
        # 线路页常见「点击进入」
        for label in ("点击进入", "进入网站", "立即进入", "点击进入网站"):
            try:
                loc = page.get_by_text(label, exact=False).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue
        if include_frames:
            parts: list[str] = []
            for frame in page.frames:
                try:
                    t = frame.inner_text("body")
                    if t and len(t.strip()) > 20:
                        parts.append(t)
                except Exception:
                    continue
            browser.close()
            return "\n".join(parts)
        text = page.inner_text("body")
        browser.close()
        return text


def discover_tip_links_sync(url: str, *, limit: int = 8) -> list[str]:
    """从页面收集疑似资料链接，供换抽取源比对。"""
    from playwright.sync_api import sync_playwright

    found: list[str] = []
    seen: set[str] = set()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(2500)
        for label in ("点击进入", "进入网站", "立即进入"):
            try:
                loc = page.get_by_text(label, exact=False).first
                if loc.count() > 0:
                    loc.click(timeout=3000)
                    page.wait_for_timeout(2000)
                    break
            except Exception:
                continue
        anchors = page.eval_on_selector_all(
            "a[href]",
            """els => els.map(a => ({href: a.href || a.getAttribute('href') || '', text: (a.innerText||'').slice(0,40)}))""",
        )
        browser.close()
    for a in anchors or []:
        href = (a.get("href") or "").strip()
        text = (a.get("text") or "").strip()
        if not href or href.startswith("javascript:"):
            continue
        abs_url = urljoin(url, href)
        if abs_url in seen:
            continue
        blob = text + " " + abs_url
        if TIP_LINK_RE.search(blob):
            seen.add(abs_url)
            found.append(abs_url)
        if len(found) >= limit:
            break
    return found


async def fetch_page_text(url: str, *, wait_ms: int = 3000, include_frames: bool = False) -> str:
    return await asyncio.to_thread(
        fetch_page_text_sync, url, wait_ms=wait_ms, include_frames=include_frames
    )


async def discover_tip_links(url: str, *, limit: int = 8) -> list[str]:
    return await asyncio.to_thread(discover_tip_links_sync, url, limit=limit)
