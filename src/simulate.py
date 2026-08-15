"""Monte Carlo engine.

Two things separate this from just reading the Dixon-Coles matrix:

1. PARAMETER UNCERTAINTY. The lambdas are estimates, not facts. Each simulated
   match draws its own (lam, mu) from a lognormal around the point estimate.
   This widens the tails the way a real forecast should: the analytical matrix
   is over-confident because it pretends we know the true scoring rates.

2. PLAYER RESOLUTION. Once a scoreline is drawn, goals are allocated to players
   via minute-weighted goal shares, giving anytime-scorer and first-scorer
   probabilities the closed form cannot produce.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from dixon_coles import RHO

PLAYERS = Path(__file__).resolve().parent.parent / "data" / "players.json"

# Lognormal sigma on each team's lambda. Captures "we do not actually know the
# post-transfer-window strength of these sides".
LAMBDA_SIGMA = 0.22


def load_players(path: Path = PLAYERS) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _weights(team_block: dict) -> tuple[list[str], np.ndarray]:
    people = team_block["xi"] + team_block.get("bench_contributors", [])
    names = [p["name"] for p in people]
    # NON moltiplicare per minutes/90: goal_share e gia una quota attesa
    # sull'INTERA partita (somma ~1.02 Roma, ~1.075 Fiorentina su XI+panchina),
    # quindi i minuti sono gia dentro. Moltiplicarli di nuovo li contava due
    # volte e schiacciava i subentranti di un fattore 2-3, cambiando
    # l'ORDINAMENTO dei marcatori e non solo la scala.
    w = np.array([p["goal_share"] for p in people], dtype=float)
    if w.sum() <= 0:
        w = np.ones(len(names))
    return names, w / w.sum()


def _tau_vec(h, a, lam, mu, rho):
    """Dixon-Coles tau evaluated elementwise on integer score arrays."""
    t = np.ones(h.shape, dtype=float)
    m00 = (h == 0) & (a == 0)
    m01 = (h == 0) & (a == 1)
    m10 = (h == 1) & (a == 0)
    m11 = (h == 1) & (a == 1)
    t[m00] = 1.0 - lam[m00] * mu[m00] * rho
    t[m01] = 1.0 + lam[m01] * rho
    t[m10] = 1.0 + mu[m10] * rho
    t[m11] = 1.0 - rho
    return t


def _draw_scores(rng, lam, mu, rho=RHO, max_rounds=40):
    """Unbiased rejection sampler for the Dixon-Coles bivariate distribution.

    Rejected draws are re-rolled as a PAIR from the unconditional Poisson, and
    acceptance is tested on every draw (not only the low-score block). Testing
    acceptance on the low block alone silently inflates the mean, because every
    rejection is replaced by an unconditionally higher draw.
    """
    n = lam.size
    h = np.zeros(n, dtype=np.int64)
    a = np.zeros(n, dtype=np.int64)
    todo = np.arange(n)

    # envelope constant: tau never exceeds this
    tau_max = float(max(1.0, 1.0 - rho, 1.0 - lam.max() * mu.max() * rho))

    for _ in range(max_rounds):
        if todo.size == 0:
            break
        hh = rng.poisson(lam[todo])
        aa = rng.poisson(mu[todo])
        t = _tau_vec(hh, aa, lam[todo], mu[todo], rho)
        acc = rng.random(todo.size) < (t / tau_max)
        h[todo[acc]] = hh[acc]
        a[todo[acc]] = aa[acc]
        todo = todo[~acc]

    if todo.size:  # vanishingly rare; accept unconditionally
        h[todo] = rng.poisson(lam[todo])
        a[todo] = rng.poisson(mu[todo])
    return h, a


def _scorer_probs(goals_team, goals_opp, names, w):
    """Exact-under-multinomial anytime probability plus first-scorer.

    anytime_i = 1 - E[(1 - w_i) ** G] where G is that team's goal count.
    Goal order is assumed exchangeable, so P(team scores the match's first
    goal | G, G_opp) = G / (G + G_opp).
    """
    counts = np.bincount(goals_team)
    gvals = np.arange(counts.size)
    pmf = counts / counts.sum()

    total = goals_team + goals_opp
    with np.errstate(invalid="ignore", divide="ignore"):
        share_first = np.where(total > 0, goals_team / np.maximum(total, 1), 0.0)
    p_team_first = float(share_first.mean())

    out = {}
    for i, nm in enumerate(names):
        anytime = float(1.0 - np.sum(pmf * (1.0 - w[i]) ** gvals))
        out[nm] = {
            "anytime": anytime,
            "expected_goals": float(w[i] * goals_team.mean()),
            "first_scorer": float(w[i] * p_team_first),
        }
    return out


def simulate(lam_home: float, lam_away: float, n: int = 200_000,
             seed: int = 42, sigma: float = LAMBDA_SIGMA,
             extra_sigma: float = 0.0) -> dict:
    rng = np.random.default_rng(seed)
    s = float(np.hypot(sigma, extra_sigma))

    # lognormal with the mean preserved: E[exp(N(-s^2/2, s))] == 1
    lh = lam_home * rng.lognormal(-0.5 * s**2, s, n)
    la = lam_away * rng.lognormal(-0.5 * s**2, s, n)

    gh, ga = _draw_scores(rng, lh, la)

    home = gh > ga
    draw = gh == ga
    away = gh < ga
    tot = gh + ga

    players = load_players()
    scorers = {}
    for team, mine, theirs in (("Roma", gh, ga), ("Fiorentina", ga, gh)):
        names, w = _weights(players[team])
        scorers[team] = _scorer_probs(mine, theirs, names, w)

    # full simulated scoreline distribution (independent of the analytical one)
    sm = np.zeros((8, 8))
    for i in range(8):
        for j in range(8):
            sm[i, j] = float(((gh == i) & (ga == j)).mean())

    return {
        "n": n,
        "sigma_used": s,
        "outcome": {
            "home": float(home.mean()),
            "draw": float(draw.mean()),
            "away": float(away.mean()),
        },
        "goals": {
            "expected_home": float(gh.mean()),
            "expected_away": float(ga.mean()),
            "expected_total": float(tot.mean()),
            "p_over_1_5": float((tot > 1.5).mean()),
            "p_over_2_5": float((tot > 2.5).mean()),
            "p_over_3_5": float((tot > 3.5).mean()),
            "p_btts": float(((gh > 0) & (ga > 0)).mean()),
            "p_home_clean_sheet": float((ga == 0).mean()),
            "p_away_clean_sheet": float((gh == 0).mean()),
        },
        "margin": {
            "p_home_by_2plus": float((gh - ga >= 2).mean()),
            "p_home_by_1": float((gh - ga == 1).mean()),
            "p_away_by_1plus": float((ga - gh >= 1).mean()),
            "mean_margin": float((gh - ga).mean()),
            "p5_margin": float(np.percentile(gh - ga, 5)),
            "p95_margin": float(np.percentile(gh - ga, 95)),
        },
        "score_matrix_mc": sm.tolist(),
        "scorers": scorers,
    }
