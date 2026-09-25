"""站点配置：历史源 + 推荐资料站。

抓取策略说明（回答「抽哪些」）：
- 不把整站全文丢进打分。
- 只保留「当期期号」相关段落，并从中抽取十二生肖关键词与一肖~九肖类型。
- 站点文案只作弱特征；抽错会被其它站与历史统计稀释，后续可用命中率回测降权。
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class TipSite:
    """生肖推荐资料站。"""

    code: str
    name: str
    entry_urls: tuple[str, ...]
    tip_urls: tuple[str, ...] = ()
    enabled: bool = True
    prefer_frames: bool = False
    note: str = ""


@dataclass(frozen=True)
class DataSource:
    """开奖数据源（非心水站）。"""

    code: str
    name: str
    url: str
    enabled: bool = True
    note: str = ""


# 历史 / 实时开奖
HISTORY_SOURCE = DataSource(
    code="history_2026",
    name="澳门2026历史开奖",
    url="https://amlskj-a.hopeojmpe.com:2088/amkjjl/2026.html",
    note="正文含期号与特码，优先用 Playwright",
)
LIVE_SOURCE = DataSource(
    code="live_data_txt",
    name="实时开奖 data.txt",
    url="https://amkj601-888.kjamzdsfdfdx.com/php/data.txt",
    note="未开奖时可能是 K/J 占位符，需跳过",
)

# 旧站 + 网站.md 新站（探测：httpx 多数可达；浏览器常跳转/线路页，tip_urls 可后续补）
TIP_SITES: tuple[TipSite, ...] = (
    TipSite(
        code="yanjiuyuan",
        name="研究院",
        entry_urls=("https://zrnilcrofy.690333hi.app:3216/#dh1",),
        tip_urls=("https://zrnilcrofy.690333hi.app:3216/main.html",),
        prefer_frames=True,
        note="旧站，已验证可抽七肖/一肖",
    ),
    TipSite(
        code="dinggeshui",
        name="定个水",
        entry_urls=("https://www.dinggeshui.com/",),
        tip_urls=(
            "https://333810.com/zl/%E4%B9%9D%E8%82%96.htm",
            "https://333810.com/",
        ),
        prefer_frames=True,
        note="入口偶发连不上，直连 tip_urls 更稳",
    ),
    TipSite(
        code="s3497",
        name="3497.com",
        entry_urls=("http://3497.com/",),
        enabled=True,
        prefer_frames=True,
        note="httpx 可达；浏览器常跳安全/线路页",
    ),
    TipSite(
        code="s2549",
        name="2549.com",
        entry_urls=("http://2549.com/", "https://2549.com/"),
        enabled=True,
        prefer_frames=True,
        note="httpx 可达",
    ),
    TipSite(
        code="s772200",
        name="772200.com",
        entry_urls=("https://772200.com/", "http://772200.com/"),
        enabled=True,
        prefer_frames=True,
        note="httpx 可达；页面易跳百科伪装站",
    ),
    TipSite(
        code="s15043",
        name="15043.cc",
        entry_urls=("https://15043.cc/",),
        enabled=True,
        prefer_frames=True,
        note="有线路匹配页，需进帧后再抽",
    ),
    TipSite(
        code="s19333",
        name="19333.com",
        entry_urls=("http://19333.com/",),
        enabled=True,
        prefer_frames=True,
        note="https 不通，用 http",
    ),
    TipSite(
        code="s590555",
        name="590555.com",
        entry_urls=("http://590555.com/", "https://590555.com/"),
        enabled=True,
        prefer_frames=True,
        note="证书/跳转不稳，作可选源",
    ),
    TipSite(
        code="s42054",
        name="42054.com",
        entry_urls=("https://42054.com/", "http://42054.com/"),
        enabled=True,
        prefer_frames=True,
        note="会跳到 ogiwz 镜像域",
    ),
)


def enabled_tip_sites() -> list[TipSite]:
    return [s for s in TIP_SITES if s.enabled]


def tip_site_by_code(code: str) -> TipSite | None:
    for s in TIP_SITES:
        if s.code == code:
            return s
    return None


def all_tip_fetch_urls(site: TipSite) -> list[str]:
    """先 tip 直链，再入口；去重保序。"""
    seen: set[str] = set()
    ordered: list[str] = []
    for u in (*site.tip_urls, *site.entry_urls):
        if u and u not in seen:
            seen.add(u)
            ordered.append(u)
    return ordered
