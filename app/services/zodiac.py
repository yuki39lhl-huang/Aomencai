from __future__ import annotations

from typing import Literal

# 十二生肖顺序（固定，用于同分打破平局）
ZODIAC_ORDER = ["鼠", "牛", "虎", "兔", "龙", "蛇", "马", "羊", "猴", "鸡", "狗", "猪"]

# 2026 马年：号码 1 起为当年生肖，向前回溯
# 马蛇龙兔虎牛鼠猪狗鸡猴羊，当年生肖 5 个号
_YEAR_2026_SEQUENCE = ["马", "蛇", "龙", "兔", "虎", "牛", "鼠", "猪", "狗", "鸡", "猴", "羊"]

RED_WAVE = {1, 2, 7, 8, 12, 13, 18, 19, 23, 24, 29, 30, 34, 35, 40, 45, 46}
BLUE_WAVE = {3, 4, 9, 10, 14, 15, 20, 25, 26, 31, 36, 37, 41, 42, 47, 48}
GREEN_WAVE = {5, 6, 11, 16, 17, 21, 22, 27, 28, 32, 33, 38, 39, 43, 44, 49}

WaveColor = Literal["红波", "蓝波", "绿波"]


def number_to_zodiac(num: int, year: int = 2026) -> str:
    if not 1 <= num <= 49:
        raise ValueError(f"号码超出范围: {num}")
    if year == 2026:
        seq = _YEAR_2026_SEQUENCE
    else:
        # 简易扩展：以马年为基准，按年份差旋转（农历生肖年）
        offset = (year - 2026) % 12
        seq = seq_rotate(_YEAR_2026_SEQUENCE, offset)
    return seq[(num - 1) % 12]


def seq_rotate(seq: list[str], offset: int) -> list[str]:
    # offset>0 表示年份往后，当年生肖前移
    if offset == 0:
        return list(seq)
    # 2027 羊年：羊排在首位……从马年序列看，向左旋一年 = 羊蛇?...
    # 马年序列首位是马；下一年首位应是羊（下一生肖）
    # 生肖正序：鼠牛虎兔龙蛇马羊猴鸡狗猪
    # 更稳妥：按当年生肖重建
    year_animal_index = (ZODIAC_ORDER.index("马") + offset) % 12
    year_animal = ZODIAC_ORDER[year_animal_index]
    # 从当年生肖往回推（与六合彩习惯一致：1=当年，2=上一年…）
    start = ZODIAC_ORDER.index(year_animal)
    backward = [ZODIAC_ORDER[(start - i) % 12] for i in range(12)]
    return backward


def zodiac_numbers(zodiac: str, year: int = 2026) -> list[int]:
    return [n for n in range(1, 50) if number_to_zodiac(n, year) == zodiac]


def wave_color(num: int) -> WaveColor:
    if num in RED_WAVE:
        return "红波"
    if num in BLUE_WAVE:
        return "蓝波"
    if num in GREEN_WAVE:
        return "绿波"
    raise ValueError(f"无法识别波色: {num}")


def extract_zodiacs_from_text(text: str) -> list[str]:
    found: list[str] = []
    for z in ZODIAC_ORDER:
        if z in text:
            found.append(z)
    return found


def tip_type_from_text(text: str) -> str | None:
    for label in ("一肖", "二肖", "三肖", "四肖", "五肖", "六肖", "七肖", "八肖", "九肖"):
        if label in text:
            return label
    return None


def draw_zodiacs(n1: int, n2: int, n3: int, n4: int, n5: int, n6: int, special: int, year: int = 2026) -> set[str]:
    """一期开奖中出现的所有生肖（平码+特码，用于包肖）。"""
    nums = [n1, n2, n3, n4, n5, n6, special]
    return {number_to_zodiac(n, year) for n in nums}


def bao_xiao_hit(zodiac: str, row: dict, year: int = 2026) -> bool:
    """包肖命中：平码或特码任一对应生肖即可。"""
    return zodiac in draw_zodiacs(
        row["n1"], row["n2"], row["n3"], row["n4"], row["n5"], row["n6"], row["special"], year
    )
