from __future__ import annotations

from datetime import date, datetime
from functools import lru_cache
from typing import Any

# 十二生肖顺序（固定，用于同分打破平局）
ZODIAC_ORDER = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

# 号码对照在春节当天换年：开奖日早于当年春节，仍按上一年的生肖。
# 开奖网站同样如此，例如 2026-02-16 的 47 期仍按蛇年，02-17 的 48 期起按马年。
# 表里没有的年份直接报错，提醒补上，不猜日期。
_SPRING_FESTIVAL = {
    2024: date(2024, 2, 10),
    2025: date(2025, 1, 29),
    2026: date(2026, 2, 17),
    2027: date(2027, 2, 6),
    2028: date(2028, 1, 26),
    2029: date(2029, 2, 13),
    2030: date(2030, 2, 3),
    2031: date(2031, 1, 23),
    2032: date(2032, 2, 11),
    2033: date(2033, 1, 31),
    2034: date(2034, 2, 19),
    2035: date(2035, 2, 8),
}

# 2026 马年为基准：生肖正序里马的位置
_BASE_YEAR = 2026
_BASE_ANIMAL = "马"


def lunar_year_for(day: date | datetime | str | None) -> int:
    """开奖日所属的生肖年。没有日期时按今天算。"""
    if day is None:
        day = date.today()
    elif isinstance(day, datetime):
        day = day.date()
    elif isinstance(day, str):
        day = date.fromisoformat(day[:10])
    festival = _SPRING_FESTIVAL.get(day.year)
    if festival is None:
        raise ValueError(f"缺少 {day.year} 年的春节日期，请在 app/services/zodiac.py 补上")
    return day.year if day >= festival else day.year - 1


@lru_cache(maxsize=None)
def _sequence(year: int) -> tuple[str, ...]:
    """号码 1 对应当年生肖，2 对应上一年，依次往回推。"""
    start = (ZODIAC_ORDER.index(_BASE_ANIMAL) + year - _BASE_YEAR) % 12
    return tuple(ZODIAC_ORDER[(start - i) % 12] for i in range(12))


def year_zodiac(year: int) -> str:
    """该生肖年占 5 个号码的那一只（号码 1、13、25、37、49）。"""
    return _sequence(year)[0]


def number_to_zodiac(num: int, year: int) -> str:
    if not 1 <= num <= 49:
        raise ValueError(f"号码超出范围: {num}")
    return _sequence(year)[(num - 1) % 12]


def zodiac_numbers(zodiac: str, year: int) -> list[int]:
    return [n for n in range(1, 50) if number_to_zodiac(n, year) == zodiac]


def draw_zodiacs(row: dict[str, Any]) -> set[str]:
    """一期开奖中出现的所有生肖（平码+特码），按该期开奖日所属的生肖年换算。"""
    year = lunar_year_for(row.get("draw_date"))
    nums = [row["n1"], row["n2"], row["n3"], row["n4"], row["n5"], row["n6"], row["special"]]
    return {number_to_zodiac(int(n), year) for n in nums}


def bao_xiao_hit(zodiac: str, row: dict[str, Any]) -> bool:
    """包肖命中：平码或特码任一对应生肖即可。"""
    return zodiac in draw_zodiacs(row)
