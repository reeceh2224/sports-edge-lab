from demo_data import mlb_board, nfl_board
from common import american_to_implied, shrink_rate
from analysis_engine import sample_reliability, recency_weight

assert len(mlb_board()) >= 3
assert len(nfl_board()) >= 3
assert abs(american_to_implied(-110) - 0.5238095238) < 1e-8
assert 0 < shrink_rate(5, 7, .25) < 1
assert sample_reliability(40) == 0.5
assert abs(recency_weight(365,365) - 0.5) < 1e-9
print('smoke tests passed')
