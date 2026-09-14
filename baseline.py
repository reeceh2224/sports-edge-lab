from dataclasses import dataclass
from common import american_to_implied, edge, confidence

@dataclass
class ModelOutput:
    projection: float
    probability: float
    confidence: float
    evidence_for: list[str]
    evidence_against: list[str]


def score_market(probability: float, projection: float, market_odds: int | None, sample_size: int, positives: list[str], negatives: list[str]):
    agreement = min(1.0, max(0.0, 0.5 + 0.08 * (len(positives) - len(negatives))))
    return {
        "projection": projection,
        "model_probability": probability,
        "implied_probability": american_to_implied(market_odds),
        "edge": edge(probability, market_odds),
        "confidence": confidence(sample_size, agreement),
        "evidence_for": positives,
        "evidence_against": negatives,
    }
