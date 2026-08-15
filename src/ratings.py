"""Team strength -> expected goals (lambda) for a single fixture.

Every knob that moves the forecast lives here as a named constant so it can be
audited, tweaked and logged. Nothing downstream invents its own adjustment.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, field
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data" / "context.json"

# --------------------------------------------------------------------------
# Tunable model constants. Each one is a hypothesis; RESULTS.md tracks which
# ones survived contact with reality.
# --------------------------------------------------------------------------

# Season-to-season regression to the mean. A team's rating index is pulled
# toward 1.0 by (1 - SHRINK). 38 games is a small sample; squads also change.
SHRINK = 0.72

# Weak nudge from long-run head-to-head at this venue. Deliberately tiny:
# H2H mostly re-encodes team quality that the ratings already carry.
H2H_WEIGHT = 0.05

# Matchday 1: fitness is uneven, new signings are not integrated, coaches are
# conservative. Slight suppression of total goals plus extra variance.
MATCHDAY1_GOAL_FACTOR = 0.97
MATCHDAY1_EXTRA_DISPERSION = 0.18

# Late-August 20:45 in Rome. Heat/humidity depresses tempo.
GOALS_HEAT_FACTOR = 0.98

# New-manager install risk: a first-season coach converts less of a squad
# upgrade into points on matchday 1.
NEW_MANAGER_DISCOUNT = 0.55

# Recency. Where a team's season splits into two clearly different halves, the
# most recent 19 games describe the current side better than the 38-game
# aggregate. Applied only to teams that have a `recent_split` block, so it is
# ASYMMETRIC whenever split data exists for one side and not the other - see
# RESULTS.md for the measured size of that bias.
RECENCY_WEIGHT = 0.40

# Dixon & Coles weight past matches by phi(t) = exp(-xi * t), t = days before
# the fixture. Their fitted xi is around 0.0065/day (half-life ~107 days), and
# that is what most open-source implementations use (see the goalmodel /
# penaltyblog / world-cup-2026-prediction-model lineage). Applied to the two
# half-season midpoints it implies a recency weight of ~0.73 - see
# recency_weight_from_decay(). We deliberately use a LOWER 0.40 because a full
# transfer window sits between then and now, which the decay curve knows
# nothing about. The sensitivity grid brackets both values.
XI_DECAY_PER_DAY = 0.0065
DAYS_TO_ANDATA_MIDPOINT = 310
DAYS_TO_RITORNO_MIDPOINT = 160


def recency_weight_from_decay(xi: float = XI_DECAY_PER_DAY) -> float:
    """The Dixon-Coles exponential-decay equivalent of RECENCY_WEIGHT.

    Not used to set the constant automatically - it is here so the arbitrary
    0.40 can be compared against the value the literature would pick.
    """
    import math
    w_old = math.exp(-xi * DAYS_TO_ANDATA_MIDPOINT)
    w_new = math.exp(-xi * DAYS_TO_RITORNO_MIDPOINT)
    return w_new / (w_new + w_old)

# Form is produced by a coach, not only by a squad. When the manager who
# generated the recent form has left, that form is only partly transferable, so
# the recency weight is scaled down for that team.
RECENCY_MANAGER_CHANGE_DISCOUNT = 0.50


@dataclass
class TeamRating:
    name: str
    attack: float          # goals scored per game / league average
    defense: float         # goals conceded per game / league average (lower = better)
    attack_raw: float
    defense_raw: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class FixtureLambdas:
    home_team: str
    away_team: str
    lam_home: float
    lam_away: float
    breakdown: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def load_context(path: Path = DATA) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def league_base(ctx: dict) -> tuple[float, float, float]:
    """Return (avg goals per team per game, home lambda base, away lambda base)."""
    gpm = ctx["league_baseline"]["goals_per_match"]
    home_share = ctx["league_baseline"]["home_goal_share"]
    return gpm / 2.0, gpm * home_share, gpm * (1.0 - home_share)


def rate_team(ctx: dict, team: str) -> TeamRating:
    """Attack/defence indices from last season, shrunk and squad-adjusted."""
    per_team_avg, _, _ = league_base(ctx)
    t = ctx["teams"][team]
    s = t["season_2526"]

    att_raw = (s["goals_for"] / s["played"]) / per_team_avg
    def_raw = (s["goals_against"] / s["played"]) / per_team_avg

    # 0) blend the full season with the most recent half, where we have it
    split = t.get("recent_split")
    if split and RECENCY_WEIGHT > 0:
        h2 = split["second_half"]
        w = RECENCY_WEIGHT
        if not split.get("manager_continuity", True):
            w *= RECENCY_MANAGER_CHANGE_DISCOUNT
        att_recent = (h2["goals_for"] / h2["played"]) / per_team_avg
        def_recent = (h2["goals_against"] / h2["played"]) / per_team_avg
        att_raw = (1 - w) * att_raw + w * att_recent
        def_raw = (1 - w) * def_raw + w * def_recent

    # 1) regress toward the league mean
    att = 1.0 + (att_raw - 1.0) * SHRINK
    dfn = 1.0 + (def_raw - 1.0) * SHRINK

    # 2) apply the squad/market delta, discounted if the coach is new
    delta = t["squad_delta_2627"]
    discount = NEW_MANAGER_DISCOUNT if t["manager"]["season_number"] == 1 else 1.0
    att *= 1.0 + delta["attack"] * discount
    dfn *= 1.0 + delta["defense"] * discount

    return TeamRating(name=team, attack=att, defense=dfn,
                      attack_raw=att_raw, defense_raw=def_raw)


def _h2h_nudge(ctx: dict) -> float:
    """Multiplicative tilt on the home lambda from all-time record at the venue.

    Returns a number near 1.0. Symmetric: the away lambda gets the inverse.
    """
    h = ctx["head_to_head"]["all_time_at_olimpico"]
    total = h["roma_wins"] + h["draws"] + h["fiorentina_wins"]
    home_win_rate = h["roma_wins"] / total
    # league-wide baseline home win rate ~0.44
    tilt = (home_win_rate - 0.44) * H2H_WEIGHT
    return 1.0 + tilt


def fixture_lambdas(ctx: dict, home: str, away: str) -> FixtureLambdas:
    _, base_home, base_away = league_base(ctx)
    rh = rate_team(ctx, home)
    ra = rate_team(ctx, away)

    lam_h = base_home * rh.attack * ra.defense
    lam_a = base_away * ra.attack * rh.defense

    nudge = _h2h_nudge(ctx)
    lam_h *= nudge
    lam_a /= nudge

    ctxf = MATCHDAY1_GOAL_FACTOR * GOALS_HEAT_FACTOR
    lam_h *= ctxf
    lam_a *= ctxf

    return FixtureLambdas(
        home_team=home, away_team=away,
        lam_home=lam_h, lam_away=lam_a,
        breakdown={
            "base_home": base_home, "base_away": base_away,
            "home_rating": rh.to_dict(), "away_rating": ra.to_dict(),
            "h2h_nudge": nudge,
            "context_factor": ctxf,
            "shrink": SHRINK,
        },
    )
