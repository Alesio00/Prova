"""Bookmaker odds handling and model/market fusion.

The market is the single most informative input available for this fixture.
Treating it as ground truth is lazy; ignoring it is worse. We de-vig it, then
fuse with the model using log-opinion pooling (geometric mean of probability
vectors), which is the standard way to combine calibrated forecasters.
"""

from __future__ import annotations

import numpy as np

# Peso del mercato de-viggato nella previsione fusa. 0.0 = solo modello,
# 1.0 = solo mercato.
#
# ERA 0.60, SCELTO A GIUDIZIO. ORA E' 1.0, E LO DICE UN BACKTEST.
#
# Su 3.031 partite di Serie A fuori campione (2017-2025, quote reali) la curva
# del log loss al variare del peso ha il minimo esattamente a peso-modello 0.0:
#
#     solo mercato      0.95112
#     fusione ottima    0.95112   (a peso modello 0.00)
#     miglioramento     0.00000
#
# Il modello non aggiunge NIENTE al mercato. Non poco: zero. Da solo fa 0.9725
# contro 0.9511 del mercato, e ogni peso positivo peggiora la fusione.
#
# Tenere 0.60 significherebbe pubblicare consapevolmente un prezzo peggiore di
# quello del banco. Il valore di questo progetto e' descrittivo - gli split, i
# duelli, la propagazione dell'incertezza - non nel prezzare.
MARKET_WEIGHT = 1.0

# Il vecchio valore, tenuto per poter riprodurre i run 001-004 e per mostrare
# nel report quanto il modello si discosterebbe se lo si lasciasse parlare.
MARKET_WEIGHT_LEGACY_JUDGEMENT = 0.60


def implied_raw(odds: dict) -> dict:
    return {k: 1.0 / v for k, v in odds.items()}


def overround(odds: dict) -> float:
    return sum(implied_raw(odds).values()) - 1.0


def devig_proportional(odds: dict) -> dict:
    """Simple normalisation. Fast, slightly biased against longshots."""
    raw = implied_raw(odds)
    s = sum(raw.values())
    return {k: v / s for k, v in raw.items()}


def devig_shin(odds: dict, iters: int = 200) -> dict:
    """Shin (1993) de-vigging: models the vig as insider-trading pressure and
    removes proportionally more margin from longshots. Closer to true prices.
    """
    raw = np.array(list(implied_raw(odds).values()))
    keys = list(odds.keys())
    s = raw.sum()
    z = 0.0
    for _ in range(iters):
        p = (np.sqrt(z**2 + 4 * (1 - z) * raw**2 / s) - z) / (2 * (1 - z))
        z_new = z + 0.5 * (p.sum() - 1.0)
        z = float(np.clip(z_new, 0.0, 0.35))
    p = (np.sqrt(z**2 + 4 * (1 - z) * raw**2 / s) - z) / (2 * (1 - z))
    p = p / p.sum()
    return {k: float(v) for k, v in zip(keys, p)}


def log_pool(model: dict, market: dict, w: float = MARKET_WEIGHT) -> dict:
    """Geometric (log-opinion) pooling of two probability vectors."""
    keys = list(model.keys())
    m = np.array([model[k] for k in keys])
    b = np.array([market[k] for k in keys])
    eps = 1e-12
    fused = np.exp((1 - w) * np.log(m + eps) + w * np.log(b + eps))
    fused /= fused.sum()
    return {k: float(v) for k, v in zip(keys, fused)}


def solve_lambdas_for_probs(target: dict, rho: float = -0.10,
                            lam0: float = 1.5, mu0: float = 1.0) -> tuple[float, float]:
    """Find (lam, mu) whose Dixon-Coles matrix reproduces a target 1X2 vector.

    Used to translate the de-vigged market back into expected goals, so the
    market can inform totals/BTTS/correct-score, not just 1X2.
    """
    from scipy.optimize import minimize
    from dixon_coles import score_matrix, outcome_probs

    def loss(v):
        lam, mu = np.exp(v)
        p = outcome_probs(score_matrix(lam, mu, rho))
        return sum((p[k] - target[k]) ** 2 for k in ("home", "draw", "away"))

    res = minimize(loss, np.log([lam0, mu0]), method="Nelder-Mead",
                   options={"xatol": 1e-6, "fatol": 1e-12, "maxiter": 4000})
    lam, mu = np.exp(res.x)
    return float(lam), float(mu)


def edge_table(fused: dict, odds: dict) -> list[dict]:
    """Expected value per unit staked at the quoted prices, plus Kelly stake."""
    rows = []
    for k, price in odds.items():
        p = fused[k]
        ev = p * price - 1.0
        b = price - 1.0
        kelly = max(0.0, (p * b - (1 - p)) / b) if b > 0 else 0.0
        rows.append({
            "selection": k, "price": price, "model_prob": p,
            "implied_prob": 1.0 / price, "ev_per_unit": ev,
            "kelly_full": kelly, "kelly_quarter": kelly / 4.0,
        })
    return rows
