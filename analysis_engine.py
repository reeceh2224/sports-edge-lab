from __future__ import annotations
from dataclasses import dataclass
from typing import Iterable
import math


def logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def weighted_signal(signals: Iterable[tuple[float, float]], intercept: float = 0.0) -> float:
    """Combine standardized signals as (value, weight) pairs into a probability."""
    score = intercept + sum(value * weight for value, weight in signals)
    return clamp(logistic(score), 0.01, 0.99)


def sample_reliability(n: float, half_strength: float = 40.0) -> float:
    """Smoothly approaches 1 as sample size grows; 0.5 at n=half_strength."""
    n = max(0.0, float(n))
    return n / (n + half_strength)


def recency_weight(days_ago: float, half_life_days: float) -> float:
    return 0.5 ** (max(0.0, days_ago) / half_life_days)


def context_weight(sample_n: int, continuity: float, days_ago: float, half_life_days: float = 365.0) -> float:
    return sample_reliability(sample_n) * clamp(continuity, 0, 1) * recency_weight(days_ago, half_life_days)


@dataclass
class Evidence:
    label: str
    direction: int
    strength: float
    sample_n: int | None = None
    note: str = ""

    @property
    def adjusted_strength(self) -> float:
        if self.sample_n is None:
            return self.strength
        return self.strength * sample_reliability(self.sample_n)


def summarize_evidence(items: list[Evidence]) -> dict:
    pos = sum(i.adjusted_strength for i in items if i.direction > 0)
    neg = sum(i.adjusted_strength for i in items if i.direction < 0)
    net = pos - neg
    agreement = abs(net) / max(0.01, pos + neg)
    return {"positive": pos, "negative": neg, "net": net, "agreement": agreement}
