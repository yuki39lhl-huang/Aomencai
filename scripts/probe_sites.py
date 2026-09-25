"""探测网站.md 与旧站点可达性。"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx

CANDIDATES = [
    ("yanjiuyuan", "https://zrnilcrofy.690333hi.app:3216/#dh1"),
    ("dinggeshui", "https://www.dinggeshui.com/"),
    ("3497", "https://3497.com/"),
    ("3497_http", "http://3497.com/"),
    ("2549", "https://2549.com/"),
    ("2549_http", "http://2549.com/"),
    ("772200", "https://772200.com/"),
    ("772200_http", "http://772200.com/"),
    ("15043", "https://15043.cc/"),
    ("15043_http", "http://15043.cc/"),
    ("19333", "https://19333.com/"),
    ("19333_http", "http://19333.com/"),
    ("590555", "https://590555.com/"),
    ("590555_http", "http://590555.com/"),
    ("42054", "https://42054.com/"),
    ("42054_http", "http://42054.com/"),
]


@dataclass
class ProbeResult:
    code: str
    url: str
    ok: bool
    status: int | None
    final_url: str
    title_hint: str
    error: str


async def probe_one(code: str, url: str) -> ProbeResult:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(
            timeout=20.0, follow_redirects=True, verify=False, headers=headers
        ) as client:
            resp = await client.get(url)
            text = resp.text[:800].replace("\n", " ")
            return ProbeResult(
                code=code,
                url=url,
                ok=resp.status_code < 400 and len(resp.text) > 50,
                status=resp.status_code,
                final_url=str(resp.url),
                title_hint=text[:120],
                error="",
            )
    except Exception as exc:
        return ProbeResult(
            code=code,
            url=url,
            ok=False,
            status=None,
            final_url="",
            title_hint="",
            error=f"{type(exc).__name__}: {exc}",
        )


async def main() -> None:
    results = await asyncio.gather(*[probe_one(c, u) for c, u in CANDIDATES])
    for r in results:
        flag = "OK" if r.ok else "FAIL"
        print(f"[{flag}] {r.code}")
        print(f"  url={r.url}")
        print(f"  status={r.status} final={r.final_url}")
        if r.error:
            print(f"  err={r.error}")
        else:
            print(f"  hint={r.title_hint[:100]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
