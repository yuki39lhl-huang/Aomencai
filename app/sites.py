"""站点配置：历史源 + 推荐资料站。

抓取策略说明（回答「抽哪些」）：
- 不把整站全文丢进打分。
- 只保留当期期号段落里「N肖」后面个数相符的生肖串。广告句里的生肖字不算。
- 同一条由短到长的阶梯，特码只留最短一档，包肖只留最长一档。
- 特码资料不进排名。包肖资料按名单均分，不再按肖数额外打折。
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
        enabled=False,
        prefer_frames=True,
        note="已禁用：只进安全/线路页，库里没有肖名单",
    ),
    TipSite(
        code="s2549",
        name="2549.com",
        entry_urls=("http://2549.com/", "https://2549.com/"),
        enabled=False,
        prefer_frames=True,
        note="已禁用：连得上但抽不到肖名单",
    ),
    TipSite(
        code="s772200",
        name="772200.com",
        entry_urls=("https://10-3.www772200a.com:8443/#111",),
        enabled=True,
        prefer_frames=True,
        note="王中王论坛入口，替代原 772200.com 首页",
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
        enabled=False,
        prefer_frames=True,
        note="已禁用：只有 http，库里没有肖名单",
    ),
    TipSite(
        code="s590555",
        name="590555.com",
        entry_urls=("https://dhrhusrmfl.690333gd.app:3137/#dh1",),
        enabled=True,
        prefer_frames=True,
        note="替代原 590555.com 首页",
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
