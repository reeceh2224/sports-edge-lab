from __future__ import annotations
import pandas as pd


def mlb_board() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "rank": 1, "game": "KC @ MIN", "market": "Hitter total bases", "selection": "Example hitter — Over 1.5",
            "projection": 2.08, "model_probability": 0.579, "bet_line": 1.5, "market_odds": 110, "sportsbook": "DraftKings (demo)", "implied_probability": 0.476,
            "edge": 0.103, "confidence": 8.1, "sample": "Strong", "status": "DEMO",
            "evidence_for": [
                "Strong results against the starter's two most-used pitch families",
                "Platoon split favors the hitter against this pitcher's handedness",
                "Projected top-three lineup slot increases expected plate appearances",
                "Opponent bullpen shows elevated recent workload"
            ],
            "evidence_against": [
                "Direct batter-vs-pitcher history is a small sample",
                "Late-game matchup could improve if a high-leverage reliever is available"
            ],
            "details": {
                "Starter lens": "Arsenal usage, velocity trend, K/BB, hard-hit profile, times-through-order",
                "Hitter lens": "Pitch-type production, handedness, rolling contact quality, lineup slot",
                "Defense lens": "OAA/range, arm strength, positioning context",
                "Catcher/baserunning": "Pop time, caught-stealing context, runner opportunity",
                "Environment": "Park/weather hooks are included when live data is available"
            }
        },
        {
            "rank": 2, "game": "BOS @ TB", "market": "Pitcher strikeouts", "selection": "Example starter — Over 5.5 K",
            "projection": 6.4, "model_probability": 0.555, "bet_line": 5.5, "market_odds": 100, "sportsbook": "Fliff (demo)", "implied_probability": 0.500,
            "edge": 0.055, "confidence": 7.4, "sample": "Good", "status": "DEMO",
            "evidence_for": [
                "Opponent projected lineup has an above-baseline strikeout profile",
                "Starter's chase-inducing secondary pitch aligns with opponent weakness",
                "Recent pitch count supports normal workload"
            ],
            "evidence_against": [
                "Opponent has several low-strikeout left-handed bats",
                "Quick hook risk if pitch count rises early"
            ],
            "details": {
                "Starter lens": "Whiff%, CSW%, pitch mix, velocity, command and workload",
                "Opponent lens": "Projected lineup K%, chase, contact and handedness",
                "Umpire": "Optional free-data hook; omitted if unavailable",
                "Bullpen": "Used as a workload/quick-hook contextual factor",
                "History": "Previous opponent meetings are recency- and sample-weighted"
            }
        },
        {
            "rank": 3, "game": "SEA @ TEX", "market": "Stolen base", "selection": "Example runner — To steal a base",
            "projection": 0.42, "model_probability": 0.367, "bet_line": 0.5, "market_odds": 210, "sportsbook": "DraftKings (demo)", "implied_probability": 0.323,
            "edge": 0.044, "confidence": 6.8, "sample": "Moderate", "status": "DEMO",
            "evidence_for": [
                "Runner attempts frequently when reaching first base",
                "Pitcher/catcher combination has a favorable running-game profile",
                "Projected game state creates multiple potential attempt windows"
            ],
            "evidence_against": [
                "Stolen-base props are highly opportunity-dependent",
                "Lineup position creates uncertainty in on-base opportunities"
            ],
            "details": {
                "Runner": "Sprint speed, attempt rate, success rate, on-base opportunity",
                "Pitcher": "Handedness, pickoff/hold context and runner advancement allowed",
                "Catcher": "Pop time, exchange/throw context and caught-stealing outcomes",
                "Game state": "Score/inning/opportunity distributions from historical plays",
                "Warning": "Model separates skill from opportunity because no reach = no attempt"
            }
        },
    ])


def nfl_board() -> pd.DataFrame:
    return pd.DataFrame([
        {
            "rank": 1, "game": "DEN @ KC", "market": "Receiving yards", "selection": "Example WR — Over 68.5",
            "projection": 82.6, "model_probability": 0.603, "bet_line": 68.5, "market_odds": -105, "sportsbook": "DraftKings (demo)", "implied_probability": 0.512,
            "edge": 0.091, "confidence": 8.0, "sample": "Strong", "status": "DEMO",
            "evidence_for": [
                "Target share rises against the defense's common coverage structure",
                "Route usage attacks an area where the defense has conceded efficient targets",
                "Coordinator-history signal points in the same direction after recency weighting",
                "Expected pass volume is above the offense's neutral baseline"
            ],
            "evidence_against": [
                "Potential bracket/double-team treatment in obvious passing situations",
                "Game-script risk if the offense plays from a large lead"
            ],
            "details": {
                "Coordinator lens": "DC history vs offense/QB, scheme continuity and personnel-adjusted samples",
                "Coverage lens": "Man/zone proxies, down-distance behavior and target outcomes",
                "Receiver lens": "Targets, air yards, route opportunity, explosive rate and red-zone work",
                "Trenches": "Pressure allowed/generated and sack/pressure outcomes where free data supports it",
                "Game context": "Pace, pass rate over expectation proxies, injuries, rest and weather hooks"
            }
        },
        {
            "rank": 2, "game": "DET @ BUF", "market": "Game total", "selection": "Example — Over 49.5",
            "projection": 53.1, "model_probability": 0.568, "bet_line": 49.5, "market_odds": -110, "sportsbook": "Fliff (demo)", "implied_probability": 0.524,
            "edge": 0.044, "confidence": 7.6, "sample": "Strong", "status": "DEMO",
            "evidence_for": [
                "Both offenses generate positive EPA in neutral situations",
                "Explosive-play profiles align with each defense's weakest allowed areas",
                "Red-zone opportunity rates are elevated"
            ],
            "evidence_against": [
                "Turnover variance can materially swing totals",
                "Weather can change the projection close to kickoff"
            ],
            "details": {
                "Offense": "EPA/play, success, explosive rate, early-down pass tendency",
                "Defense": "EPA allowed, success allowed, explosive suppression, red-zone rate",
                "Coaching": "OC/DC historical tendency and continuity context",
                "Situational": "Neutral script, trailing/leading splits, down-distance tendencies",
                "Environment": "Rest, travel, surface and weather hooks"
            }
        },
        {
            "rank": 3, "game": "NYG @ DAL", "market": "QB passing attempts", "selection": "Example QB — Over 34.5",
            "projection": 37.2, "model_probability": 0.551, "bet_line": 34.5, "market_odds": 100, "sportsbook": "DraftKings (demo)", "implied_probability": 0.500,
            "edge": 0.051, "confidence": 7.0, "sample": "Good", "status": "DEMO",
            "evidence_for": [
                "Opponent has historically forced elevated pass volume in comparable game scripts",
                "Offense's early-down pass tendency is above league baseline",
                "Backfield usage suggests fewer designed rushes"
            ],
            "evidence_against": [
                "Efficiency could reduce total play volume if drives end quickly",
                "A close/leading script could lower second-half attempts"
            ],
            "details": {
                "Volume": "Plays/game, situation-neutral pass rate and pace",
                "Defense": "Opponent run/pass funnel indicators",
                "Coordinator": "OC and DC historical tendency, weighted toward current scheme",
                "QB": "Dropbacks, sacks, scrambles and attempts by game state",
                "Uncertainty": "Game script modeled explicitly rather than treated as certain"
            }
        },
    ])


def source_table() -> pd.DataFrame:
    return pd.DataFrame([
        ["MLB Baseball Savant / Statcast", "MLB", "Pitch-level tracking and batted-ball data", "$0", "Primary"],
        ["pybaseball", "MLB", "Python access to public baseball datasets", "$0", "Connector"],
        ["MLB Stats API", "MLB", "Schedules, rosters, game metadata / probable starters", "$0", "Current-game metadata"],
        ["nflverse / nflfastR datasets", "NFL", "Play-by-play, players, schedules and derived public data", "$0", "Primary"],
        ["Public official team/league pages", "NFL/MLB", "Coach, roster, injury and transaction verification", "$0", "Supplemental"],
        ["Public odds webpages", "NFL/MLB", "VegasInsider team markets + DraftKings Network/RotoWire public prop pages when exposed", "$0", "Live lines / props"],
        ["Manual odds entry", "Both", "Fallback if the free live-odds quota is unavailable", "$0", "Market comparison"],
    ], columns=["Source", "Sport", "Purpose", "Cost", "Role"])


def mlb_bet_explorer() -> pd.DataFrame:
    return pd.DataFrame([
        {"game":"KC @ MIN","player":"Example hitter","category":"Player prop","market":"Hits","selection":"Over 1.5 hits","line":1.5,"projection":1.72,"model_probability":0.493,"confidence":7.2,"verdict":"Lean","sample":"Good","why_good":["Projected for a top-three lineup spot and 4–5 plate appearances","Contact profile matches the starter's most-used fastball family","Opponent infield defense grades as a mild positive matchup in the model"],"why_bad":["Two-hit props require both skill and enough plate appearances","Direct history against this pitcher is too small to carry much weight"]},
        {"game":"KC @ MIN","player":"Example hitter","category":"Player prop","market":"Total bases","selection":"Over 1.5 total bases","line":1.5,"projection":2.08,"model_probability":0.579,"confidence":8.1,"verdict":"Strong lean","sample":"Strong","why_good":["Strong pitch-type matchup against the starter's two primary offerings","Platoon split favors the hitter","Bullpen workload increases the chance of facing a lower-leverage reliever later"],"why_bad":["Extra-base outcomes are volatile","A late elite reliever could materially reduce the edge"]},
        {"game":"KC @ MIN","player":"Example hitter","category":"Player prop","market":"Home run","selection":"To hit a home run","line":0.5,"projection":0.24,"model_probability":0.224,"confidence":5.8,"verdict":"Pass","sample":"Moderate","why_good":["Hard-hit profile is favorable against this pitcher's fastball location tendency","Park context does not suppress right-handed power"],"why_bad":["Home runs are low-frequency events with large variance","Pitcher limits barrels better than his ERA alone suggests"]},
        {"game":"KC @ MIN","player":"Example runner","category":"Player prop","market":"Stolen base","selection":"To steal a base","line":0.5,"projection":0.42,"model_probability":0.367,"confidence":6.8,"verdict":"Lean","sample":"Moderate","why_good":["Runner attempts frequently after reaching first","Pitcher/catcher pairing creates an above-average attempt environment","Runner speed and recent opportunity are favorable"],"why_bad":["No on-base event means no steal opportunity","Game state can erase attempts even when the matchup is favorable"]},
        {"game":"KC @ MIN","player":"Example starter","category":"Pitcher prop","market":"Strikeouts","selection":"Over 5.5 strikeouts","line":5.5,"projection":5.9,"model_probability":0.536,"confidence":6.9,"verdict":"Small lean","sample":"Good","why_good":["Opponent projected lineup has several above-average strikeout bats","Starter's best chase pitch attacks a lineup weakness"],"why_bad":["Pitch count efficiency has been inconsistent","Multiple contact-oriented left-handed hitters lower the ceiling"]},
        {"game":"KC @ MIN","player":"Game","category":"Game market","market":"Moneyline","selection":"KC moneyline","line":None,"projection":0.54,"model_probability":0.540,"confidence":6.6,"verdict":"Price dependent","sample":"Strong","why_good":["Starting-pitcher matchup is slightly favorable","Projected top of lineup creates an offensive advantage"],"why_bad":["Bullpen gap is close to neutral","Without an entered sportsbook price, value cannot be determined"]},
        {"game":"KC @ MIN","player":"Game","category":"Game market","market":"Total runs","selection":"Over 8.5 runs","line":8.5,"projection":8.9,"model_probability":0.548,"confidence":6.4,"verdict":"Small lean","sample":"Strong","why_good":["Both projected lineups make above-average contact against the probable starters","Bullpen workload raises late-run potential"],"why_bad":["Run totals are sensitive to confirmed lineups and weather","One dominant starter outing can invalidate the offensive assumptions"]},
    ])


def nfl_bet_explorer() -> pd.DataFrame:
    return pd.DataFrame([
        {"game":"DEN @ KC","player":"Example WR","category":"Player prop","market":"Receiving yards","selection":"Over 68.5 receiving yards","line":68.5,"projection":82.6,"model_probability":0.603,"confidence":8.0,"verdict":"Strong lean","sample":"Strong","why_good":["Target share rises against the defense's common coverage structure","Route tree attacks the defense's weakest target area","Coordinator-history signal agrees after recency weighting","Expected pass volume is above neutral baseline"],"why_bad":["Potential bracket coverage on obvious passing downs","Large-lead game script could reduce second-half passing"]},
        {"game":"DEN @ KC","player":"Example WR","category":"Player prop","market":"Receptions","selection":"Over 5.5 receptions","line":5.5,"projection":6.3,"model_probability":0.564,"confidence":7.4,"verdict":"Lean","sample":"Strong","why_good":["Short/intermediate target profile fits opponent coverage tendencies","Receiver owns a strong share of first-read targets"],"why_bad":["Explosive completions could produce yards without enough catches","Double-team treatment can shift underneath targets elsewhere"]},
        {"game":"DEN @ KC","player":"Example WR","category":"Player prop","market":"Longest reception","selection":"Over 24.5 yards","line":24.5,"projection":27.8,"model_probability":0.547,"confidence":6.3,"verdict":"Small lean","sample":"Moderate","why_good":["Defense has allowed explosive completions from similar alignments","Receiver's air-yard profile creates multiple deep opportunities"],"why_bad":["Longest-reception props are highly volatile","Safety structure can eliminate the exact route families needed"]},
        {"game":"DEN @ KC","player":"Example QB","category":"Player prop","market":"Passing yards","selection":"Over 278.5 passing yards","line":278.5,"projection":291.4,"model_probability":0.555,"confidence":7.1,"verdict":"Lean","sample":"Strong","why_good":["Opponent's defensive structure encourages underneath completions and sustained passing volume","Neutral-situation pass rate projects above league average","Protection matchup is acceptable in the current model"],"why_bad":["A comfortable lead could reduce attempts","Sack/pressure volatility can lower passing volume quickly"]},
        {"game":"DEN @ KC","player":"Example RB","category":"Player prop","market":"Rushing yards","selection":"Over 61.5 rushing yards","line":61.5,"projection":57.2,"model_probability":0.438,"confidence":7.0,"verdict":"Avoid over","sample":"Good","why_good":["Potential positive game script creates late rushing volume"],"why_bad":["Opponent run defense is stronger than its raw yards allowed suggest","Backfield split reduces expected carries","Offense projects to attack through the air more often"]},
        {"game":"DEN @ KC","player":"Game","category":"Game market","market":"Spread","selection":"KC -3.5","line":-3.5,"projection":4.7,"model_probability":0.552,"confidence":6.9,"verdict":"Small lean","sample":"Strong","why_good":["Efficiency matchup favors KC on early downs","Home-field and offensive consistency are positive inputs"],"why_bad":["One-score NFL games create meaningful spread variance","Turnovers and special teams are difficult to project precisely"]},
        {"game":"DEN @ KC","player":"Game","category":"Game market","market":"Game total","selection":"Over 47.5 points","line":47.5,"projection":49.8,"model_probability":0.547,"confidence":6.5,"verdict":"Small lean","sample":"Strong","why_good":["Both offenses project above neutral efficiency baselines","Explosive-play pathways exist for both teams"],"why_bad":["Red-zone variance can turn efficient drives into field goals","Weather and late injury news can move the total materially"]},
    ])
