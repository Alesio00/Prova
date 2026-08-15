"""Dixon-Coles score matrix.

Plain independent Poisson under-predicts 0-0/1-1 and over-predicts 1-0/0-1.
Dixon & Coles (1997) fix this with a low-score correction tau. Everything the
report shows (1X2, over/under, BTTS, handicaps) is a projection of this matrix.
"""

from __future__ import annotations

import numpy as np
from scipy.stats import poisson

# Dixon-Coles dependence parameter. Negative rho => more draws at low scores,
# which is what Serie A historically shows. -0.10 is the usual fitted range.
RHO = -0.10

MAX_GOALS = 12


def tau(x: int, y: int, lam: float, mu: float, rho: float = RHO) -> float:
    """Low-score correction, defined only on the 2x2 block {0,1}x{0,1}."""
    if x == 0 and y == 0:
        return 1.0 - lam * mu * rho
    if x == 0 and y == 1:
        return 1.0 + lam * rho
    if x == 1 and y == 0:
        return 1.0 + mu * rho
    if x == 1 and y == 1:
        return 1.0 - rho
    return 1.0


def score_matrix(lam: float, mu: float, rho: float = RHO,
                 max_goals: int = MAX_GOALS) -> np.ndarray:
    """P[i, j] = probability of home i goals, away j goals."""
    h = poisson.pmf(np.arange(max_goals + 1), lam)
    a = poisson.pmf(np.arange(max_goals + 1), mu)
    m = np.outer(h, a)
    for i in (0, 1):
        for j in (0, 1):
            m[i, j] *= tau(i, j, lam, mu, rho)
    return m / m.sum()


def outcome_probs(m: np.ndarray) -> dict:
    return {
        "home": float(np.tril(m, -1).sum()),
        "draw": float(np.trace(m)),
        "away": float(np.triu(m, 1).sum()),
    }


def totals(m: np.ndarray, line: float = 2.5) -> dict:
    n = m.shape[0]
    idx = np.add.outer(np.arange(n), np.arange(n))
    over = float(m[idx > line].sum())
    return {f"over_{line}": over, f"under_{line}": 1.0 - over}


def btts(m: np.ndarray) -> dict:
    yes = float(m[1:, 1:].sum())
    return {"btts_yes": yes, "btts_no": 1.0 - yes}


def asian_handicap(m: np.ndarray, line: float) -> dict:
    """Home team handicap. Positive line = home gives away a start.

    Returns win/push/loss probability for backing the HOME side at `line`.
    """
    n = m.shape[0]
    diff = np.subtract.outer(np.arange(n), np.arange(n)) + line
    return {
        "home_cover": float(m[diff > 0].sum()),
        "push": float(m[diff == 0].sum()),
        "home_lose": float(m[diff < 0].sum()),
    }


def top_scorelines(m: np.ndarray, k: int = 10) -> list[dict]:
    flat = [(i, j, float(m[i, j])) for i in range(m.shape[0]) for j in range(m.shape[1])]
    flat.sort(key=lambda t: -t[2])
    return [{"score": f"{i}-{j}", "prob": p} for i, j, p in flat[:k]]


def clean_sheets(m: np.ndarray) -> dict:
    return {
        "home_clean_sheet": float(m[:, 0].sum()),
        "away_clean_sheet": float(m[0, :].sum()),
    }
