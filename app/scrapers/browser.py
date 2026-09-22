"""Windows + uvicorn 下 async Playwright 会因事件循环无法起子进程而 NotImplementedError。
统一用同步 Playwright，放到线程里跑。
"""
from __future__ import annotations

import asyncio


def fetch_page_text_sync(url: str, *, wait_ms: int = 3000, include_frames: bool = False) -> str:
    from playwright.sync_api import sync_playwright

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(wait_ms)
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


async def fetch_page_text(url: str, *, wait_ms: int = 3000, include_frames: bool = False) -> str:
    return await asyncio.to_thread(
        fetch_page_text_sync, url, wait_ms=wait_ms, include_frames=include_frames
    )
