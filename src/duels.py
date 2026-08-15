"""Player-versus-player layer.

Three questions, three different computations - they are not the same thing and
conflating them is how "who wins the duel" turns into astrology:

1. WHO ACTUALLY MEETS WHOM. A duel matrix over all 11x11 pairs, weighted by how
   often the two are in the same part of the pitch at the same phase of play.
   Most of the 121 pairs are near-zero: a left wing-back and the opposite
   full-back barely interact. Contest weight comes first, quality second.

2. WHO SCORES, JOINTLY. For every cross-team pair of players, the probability
   that both find the net. Taken from the simulation, not from multiplying two
   marginals - the shared lambda uncertainty makes them positively correlated.

3. THE SINGLE MOST LIKELY MATCH STORY. Enumerating every combination of
   scoreline and goal attribution and asking which one specific outcome is most
   probable. The honest answer is dominated by how flat this distribution is.

Availability risk is applied here rather than in the team model, because that
is where it actually bites: a missing Kean changes who scores far more than it
changes whether Fiorentina score.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

PLAYERS = Path(__file__).resolve().parent.parent / "data" / "players.json"

# --- duel model constants -------------------------------------------------

# Lateral tolerance. Two players a full third of the pitch apart contest
# roughly e^-2 as often as two directly opposed.
LANE_SIGMA = 0.22

# How much of the match each line pairing spends contesting the other.
# Rows: home player's line, cols: away player's line. 0 GK, 1 DEF, 2 MID, 3 ATT.
LINE_CONTEST = np.array([
    [0.00, 0.00, 0.02, 0.10],   # GK vs ...
    [0.00, 0.04, 0.22, 0.90],   # DEF vs ...
    [0.02, 0.22, 0.75, 0.30],   # MID vs ...
    [0.10, 0.90, 0.30, 0.05],   # ATT vs ...
])

# Logistic slope converting a quality gap into a duel win probability.
DUEL_SLOPE = 1.9


def load(path: Path = PLAYERS) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def squad(data: dict, team: str, bench: bool = False) -> list[dict]:
    p = list(data[team]["xi"])
    if bench:
        p += data[team].get("bench_contributors", [])
    return p


# --------------------------------------------------------------------------
# 1. duel matrix
# --------------------------------------------------------------------------

# Normaliser so that an average attacking starter scores ~1.0 on the threat
# scale, which is the same scale def_rating lives on. Set by _prime() from the
# actual squads; the raw goal/assist shares are shares of a team total and mean
# nothing until they are put on a common scale with the defenders.
_THREAT_NORM = 1.0


def _threat(p: dict) -> float:
    """Attacking output index. ~1.0 = average attacking starter."""
    return (p["goal_share"] * 2.2 + p["assist_share"]) / _THREAT_NORM


def contest_weight(a: dict, b: dict) -> float:
    """How often these two are in the same duel. Lanes are mirrored: the home
    player's left attacks the away player's right, so the two lane values of an
    opposing pair sum to 1.0 when they are directly opposed."""
    lane = np.exp(-((a["lane"] + b["lane"] - 1.0) ** 2) / (2 * LANE_SIGMA ** 2))
    line = LINE_CONTEST[a["line"], b["line"]]
    minutes = (a["minutes"] / 90.0) * (b["minutes"] / 90.0)
    return float(lane * line * minutes)


def duel_edge(a: dict, b: dict) -> float:
    """P(the home player comes out ahead).

    Whoever is further forward is the one attacking, so his threat is measured
    against the other's defensive rating. On equal lines the two are compared on
    the sum of both qualities.
    """
    if a["line"] > b["line"]:            # home player attacking
        gap = _threat(a) - b["def_rating"]
    elif b["line"] > a["line"]:          # away player attacking
        gap = a["def_rating"] - _threat(b)
    else:
        gap = ((_threat(a) + a["def_rating"])
               - (_threat(b) + b["def_rating"])) * 0.5
    return float(1.0 / (1.0 + np.exp(-DUEL_SLOPE * gap)))


def duel_matrix(data: dict, home: str = "Roma", away: str = "Fiorentina") -> dict:
    H, A = squad(data, home), squad(data, away)
    rows = []
    for a in H:
        for b in A:
            w = contest_weight(a, b)
            if w < 0.01:
                continue
            e = duel_edge(a, b)
            rows.append({
                "home_player": a["name"], "home_pos": a["pos"],
                "away_player": b["name"], "away_pos": b["pos"],
                "contest_weight": w,
                "home_edge": e,
                # how much this duel can swing the match: frequent AND lopsided
                "leverage": w * abs(e - 0.5) * 2.0,
            })
    rows.sort(key=lambda r: -r["leverage"])
    total = sum(r["contest_weight"] for r in rows) or 1.0
    for r in rows:
        r["share_of_duels"] = r["contest_weight"] / total
    return {
        "pairs_evaluated": len(H) * len(A),
        "pairs_that_actually_meet": len(rows),
        "duels": rows,
    }


def zone_summary(matrix: dict) -> list[dict]:
    """Aggregate the duel matrix into pitch zones, which is what a coach
    actually acts on. A single duel is noise; a zone losing 60/40 is a plan."""
    zones = {"Fascia sinistra Roma": (0.0, 0.34), "Centro": (0.34, 0.66),
             "Fascia destra Roma": (0.66, 1.0)}
    out = []
    for name, (lo, hi) in zones.items():
        sel = [d for d in matrix["duels"]
               if lo <= _lane_of(d["home_player"]) < hi]
        if not sel:
            continue
        w = sum(d["contest_weight"] for d in sel)
        edge = sum(d["home_edge"] * d["contest_weight"] for d in sel) / w
        out.append({"zone": name, "weight": w, "roma_edge": edge,
                    "n_duels": len(sel)})
    return out


_LANE_CACHE: dict[str, float] = {}


def _lane_of(name: str) -> float:
    return _LANE_CACHE.get(name, 0.5)


def _prime(data: dict) -> None:
    """Cache lanes and set the threat normaliser from the two squads."""
    global _THREAT_NORM
    raw = []
    for team in ("Roma", "Fiorentina"):
        for p in squad(data, team, bench=True):
            _LANE_CACHE[p["name"]] = p["lane"]
            if p["line"] >= 3:
                raw.append(p["goal_share"] * 2.2 + p["assist_share"])
    _THREAT_NORM = float(np.mean(raw)) if raw else 1.0


# --------------------------------------------------------------------------
# 2 & 3. joint scorer distribution and the most likely match story
# --------------------------------------------------------------------------

def _shares(players: list[dict]) -> tuple[list[str], np.ndarray]:
    names = [p["name"] for p in players]
    # vedi simulate._weights: goal_share e gia una quota sull'intera partita
    w = np.array([p["goal_share"] for p in players], dtype=float)
    return names, w / w.sum()


def _apply_availability(data: dict, team: str, rng, n: int) -> tuple[list[str], np.ndarray, np.ndarray]:
    """Return (names, per-sim weight matrix, per-sim team lambda multiplier).

    A player who may not be at the club on matchday gets his goal share moved
    to his named replacement in the simulations where he is absent, and the
    team's scoring rate takes a small hit reflecting the drop in quality.
    """
    players = squad(data, team, bench=True)
    names, base = _shares(players)
    idx = {nm: i for i, nm in enumerate(names)}
    W = np.tile(base, (n, 1))
    mult = np.ones(n)

    for who, risk in data.get("availability_risk", {}).items():
        if who not in idx:
            continue
        out = rng.random(n) > risk["p_available"]
        if not out.any():
            continue
        rep = risk.get("replacement")
        i = idx[who]
        moved = W[out, i]
        W[out, i] = 0.0
        if rep in idx:
            W[out, idx[rep]] += moved
        # quality drop: the replacement is worse than the man he replaces
        mult[out] *= 0.94
    W /= W.sum(axis=1, keepdims=True)
    return names, W, mult


def _assign_goals(rng, W, counts, n_players):
    """Vectorised multinomial allocation of each team's goals to its players.

    Returns an (n, n_players) matrix of goals per player. Looping in Python
    over 400k simulations to call rng.choice is what makes a naive version of
    this slow; inverse-CDF sampling over the whole array is ~50x faster.
    """
    n = counts.size
    out = np.zeros((n, n_players), dtype=np.int8)
    max_g = int(counts.max())
    if max_g == 0:
        return out
    cum = np.cumsum(W, axis=1)
    cum[:, -1] = 1.0
    for k in range(max_g):
        live = counts > k
        if not live.any():
            break
        u = rng.random(live.sum())
        pick = (u[:, None] > cum[live]).sum(axis=1)
        np.add.at(out, (np.flatnonzero(live), np.minimum(pick, n_players - 1)), 1)
    return out


def simulate_stories(lam_home: float, lam_away: float, data: dict,
                     n: int = 400_000, seed: int = 11) -> dict:
    """Monte Carlo over scorelines AND goal attribution, with availability risk.

    Every distinct (scoreline, who scored) combination is a separate outcome.
    There are tens of thousands of them, which is the finding: asking for "the
    most likely player-vs-player outcome" has an answer, but the answer carries
    a few percent of the probability mass at best.
    """
    rng = np.random.default_rng(seed)

    hn, HW, hmult = _apply_availability(data, "Roma", rng, n)
    an, AW, amult = _apply_availability(data, "Fiorentina", rng, n)

    gh = rng.poisson(lam_home * hmult)
    ga = rng.poisson(lam_away * amult)

    Ch = _assign_goals(rng, HW, gh, len(hn))
    Ca = _assign_goals(rng, AW, ga, len(an))

    # every distinct full attribution, counted exactly
    C = np.concatenate([Ch, Ca], axis=1)
    uniq, cnt = np.unique(C, axis=0, return_counts=True)
    order = np.argsort(-cnt)

    total = float(n)
    top = []
    for i in order[:15]:
        row = uniq[i]
        h_part, a_part = row[:len(hn)], row[len(hn):]
        top.append({
            "score": f"{int(h_part.sum())}-{int(a_part.sum())}",
            "roma_scorers": _fmt_counts(h_part, hn) or "nessuno",
            "fiorentina_scorers": _fmt_counts(a_part, an) or "nessuno",
            "prob": float(cnt[i] / total),
        })

    scoring = [s for s in top if s["score"] != "0-0"]

    # joint scorer pairs, straight from the simulation (not marginal products)
    sh = (Ch > 0)
    sa = (Ca > 0)
    pair = sh.T.astype(np.int32) @ sa.astype(np.int32) / total
    pairs = [{"roma": hn[i], "fiorentina": an[j], "p_both_score": float(pair[i, j])}
             for i in range(len(hn)) for j in range(len(an)) if pair[i, j] > 0.002]
    pairs.sort(key=lambda r: -r["p_both_score"])

    # marginal anytime, for reference alongside the pairs
    anytime = {
        "Roma": {hn[i]: float(sh[:, i].mean()) for i in range(len(hn))},
        "Fiorentina": {an[j]: float(sa[:, j].mean()) for j in range(len(an))},
    }

    return {
        "n": n,
        "distinct_stories": int(uniq.shape[0]),
        "top_stories": top,
        "most_likely_scoring_story": scoring[0] if scoring else None,
        "top_scorer_pairs": pairs[:15],
        "anytime": anytime,
        "p_no_scorer_at_all": float(((gh == 0) & (ga == 0)).mean()),
        "concentration": {
            "top1": top[0]["prob"],
            "top10_cumulative": float(sum(s["prob"] for s in top[:10])),
            "stories_to_cover_50pct": int(
                np.searchsorted(np.cumsum(np.sort(cnt)[::-1]) / total, 0.50) + 1),
        },
    }


def _fmt_counts(row, names) -> str:
    parts = [f"{names[i]}{'' if row[i] == 1 else f' x{int(row[i])}'}"
             for i in np.flatnonzero(row)]
    return ", ".join(parts)


def _fmt(idxs: np.ndarray, names: list[str]) -> str:
    if len(idxs) == 0:
        return ""
    c = Counter(names[i] for i in idxs)
    return ", ".join(f"{k}{'' if v == 1 else f' x{v}'}" for k, v in sorted(c.items()))


# --------------------------------------------------------------------------

def run(lam_home: float, lam_away: float, n: int = 400_000, seed: int = 11) -> dict:
    data = load()
    _prime(data)
    m = duel_matrix(data)
    return {
        "duel_matrix": m,
        "zones": zone_summary(m),
        "stories": simulate_stories(lam_home, lam_away, data, n=n, seed=seed),
    }
