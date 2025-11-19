"""Assorted helper utilities."""

from __future__ import annotations

from astrbot.core.message.components import At
from astrbot.api.event import AstrMessageEvent
from typing import Iterable, Optional
import math
import time


def now_ts() -> float:
    return time.time()


def format_currency(amount: int) -> str:
    units = ["", "万", "亿"]
    abs_amount = abs(amount)
    idx = 0
    val = float(abs_amount)
    while val >= 10000 and idx < len(units) - 1:
        val /= 10000
        idx += 1
    formatted = f"{val:.2f}".rstrip("0").rstrip(".")
    prefix = "-" if amount < 0 else ""
    return f"{prefix}{formatted}{units[idx]} 金币"


def extract_first_at(event: AstrMessageEvent) -> Optional[str]:
    """Fetch the first @ mention id from the incoming message chain."""

    for seg in event.get_messages():
        if isinstance(seg, At) and seg.qq not in ("all", "here"):
            return str(seg.qq)
    return None


def normalize_amount(text: str) -> int:
    text = text.strip()
    if text.endswith("万"):
        return int(float(text[:-1]) * 10000)
    if text.endswith("亿"):
        return int(float(text[:-1]) * 100000000)
    return int(text)


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def chunked(items: Iterable, size: int):
    bucket = []
    for item in items:
        bucket.append(item)
        if len(bucket) == size:
            yield bucket
            bucket = []
    if bucket:
        yield bucket


__all__ = [
    "now_ts",
    "format_currency",
    "extract_first_at",
    "normalize_amount",
    "clamp",
    "chunked",
]
