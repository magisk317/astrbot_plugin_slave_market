"""Simple cyclic weather generator."""

from __future__ import annotations

import random
import time
from dataclasses import dataclass


@dataclass(slots=True)
class WeatherEffect:
    name: str
    description: str
    crop_growth: float
    work_income: float


@dataclass(slots=True)
class SeasonEffect:
    name: str
    description: str
    crop_growth: float


class WeatherService:
    def __init__(self, refresh_interval: int = 3600):
        self.refresh_interval = refresh_interval
        self._state: dict | None = None
        self._updated_at = 0.0
        self._weather_candidates = [
            WeatherEffect("晴朗", "阳光普照，适合劳作。", 1.1, 1.1),
            WeatherEffect("小雨", "细雨滋润，作物成长提升。", 1.25, 0.95),
            WeatherEffect("暴雪", "暴雪肆虐，行动困难。", 0.7, 0.8),
            WeatherEffect("大风", "狂风四起，出行需谨慎。", 0.9, 1.0),
            WeatherEffect("热浪", "闷热难耐，打工效率下降。", 0.85, 0.75),
        ]
        self._season_candidates = [
            SeasonEffect("春季", "春暖花开，适合播种。", 1.2),
            SeasonEffect("夏季", "高温多雨，作物生长迅速。", 1.1),
            SeasonEffect("秋季", "丰收季节，收益稳定。", 1.0),
            SeasonEffect("冬季", "寒风萧瑟，作物减速。", 0.8),
        ]

    def get_status(self) -> dict:
        now = time.time()
        if not self._state or now - self._updated_at > self.refresh_interval:
            self._state = self._generate()
            self._updated_at = now
        return self._state

    def _generate(self) -> dict:
        weather = random.choice(self._weather_candidates)
        season = random.choice(self._season_candidates)
        temperature = random.randint(-10, 38)
        return {
            "weather": weather,
            "season": season,
            "temperature": temperature,
            "crop_rate": weather.crop_growth * season.crop_growth,
            "work_rate": weather.work_income,
            "updated_at": time.time(),
        }
