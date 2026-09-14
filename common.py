import math

def american_to_implied(odds: int | float | None):
    if odds is None or odds == 0:
        return None
    odds = float(odds)
    if odds > 0:
        return 100.0 / (odds + 100.0)
    return (-odds) / ((-odds) + 100.0)

def edge(model_probability: float, odds: int | float | None):
    implied = american_to_implied(odds)
    return None if implied is None else model_probability - implied

def shrink_rate(successes: float, attempts: float, league_rate: float, prior_weight: float = 25.0):
    """Bayesian-style shrinkage prevents tiny matchup samples from dominating."""
    return (successes + prior_weight * league_rate) / (attempts + prior_weight)

def confidence(sample_size: float, agreement_score: float, injury_uncertainty: float = 0.0):
    sample_component = min(1.0, math.log1p(max(0, sample_size)) / math.log(101))
    value = 10 * (0.55 * sample_component + 0.45 * agreement_score) - 2.5 * injury_uncertainty
    return max(0.0, min(10.0, value))
