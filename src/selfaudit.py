"""The model auditing itself.

Every other module answers "what is the probability". This one answers the
question that actually decides whether the output is usable:

    HOW MUCH OF THIS NUMBER IS THE DATA, AND HOW MUCH IS ME?

The method is uncertainty propagation. Every constant I chose by judgement and
every input I estimated rather than sourced gets a plausible range instead of a
point value. Thousands of draws from those ranges produce a DISTRIBUTION of
forecasts rather than one forecast. Three things fall out:

  1. A credible interval on P(Roma win) that includes model uncertainty, not
     just match randomness. The headline number alone hides this entirely.

  2. A variance decomposition: which input is responsible for the spread. This
     is the priority list for the next round of work, derived rather than
     guessed.

  3. DECISION STABILITY. Over all draws, how often does the recommendation
     flip? A conclusion that survives 95% of the plausible parameter space is
     worth acting on. One that survives 55% is a coin flip wearing a decimal
     point.

Point 3 is the deliverable. A forecast that cannot say how fragile it is has
not finished the job.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

import dixon_coles as dc
import market as mk
import ratings

RESULTS = Path(__file__).resolve().parent.parent / "results"

# Plausible ranges for everything chosen by judgement. Each range is meant to
# be the interval a competent, differently-opinionated analyst might pick -
# not a confidence interval, and deliberately not narrow.
RANGES = {
    "SHRINK": (0.55, 0.90),
    # brackets our 0.40 and the Dixon-Coles decay value of 0.73
    "RECENCY_WEIGHT": (0.20, 0.78),
    "RECENCY_MANAGER_CHANGE_DISCOUNT": (0.30, 0.80),
    "NEW_MANAGER_DISCOUNT": (0.30, 0.85),
    "MATCHDAY1_GOAL_FACTOR": (0.93, 1.00),
    "H2H_WEIGHT": (0.00, 0.15),
    "GOALS_HEAT_FACTOR": (0.96, 1.00),
}
MARKET_WEIGHT_RANGE = (0.40, 0.80)
RHO_RANGE = (-0.14, -0.06)
HOME_SHARE_RANGE = (0.535, 0.575)

# Data we estimated rather than sourced.
DATA_RANGES = {
    ("Roma", "goals_for"): (50, 58),
    ("Roma", "goals_against"): (30, 37),
    ("Fiorentina", "goals_for"): (35, 46),
    ("Fiorentina", "goals_against"): (46, 56),
}
FIO_DELTA_ATT = (0.00, 0.14)
ROMA_DELTA_ATT = (-0.02, 0.08)
# multiplier on the derived (not sourced) Fiorentina ritorno goal split
FIO_RITORNO_SCALE = (0.85, 1.15)


def _draw(rng, lo, hi):
    return float(rng.uniform(lo, hi))


def audit(n: int = 4000, seed: int = 99) -> dict:
    rng = np.random.default_rng(seed)
    base_ctx = ratings.load_context()
    odds = base_ctx["market"]["decimal_odds"]

    originals = {k: getattr(ratings, k) for k in RANGES}
    orig_mw = mk.MARKET_WEIGHT

    samples, draws = [], []
    try:
        for _ in range(n):
            d = {k: _draw(rng, *v) for k, v in RANGES.items()}
            for k, v in d.items():
                setattr(ratings, k, v)
            d["MARKET_WEIGHT"] = _draw(rng, *MARKET_WEIGHT_RANGE)
            d["RHO"] = _draw(rng, *RHO_RANGE)

            ctx = json.loads(json.dumps(base_ctx))
            ctx["league_baseline"]["home_goal_share"] = d["home_goal_share"] = \
                _draw(rng, *HOME_SHARE_RANGE)
            for (team, field), rangev in DATA_RANGES.items():
                val = _draw(rng, *rangev)
                ctx["teams"][team]["season_2526"][field] = val
                d[f"{team}_{field}"] = val

            d["fio_delta_att"] = _draw(rng, *FIO_DELTA_ATT)
            ctx["teams"]["Fiorentina"]["squad_delta_2627"]["attack"] = d["fio_delta_att"]
            ctx["teams"]["Fiorentina"]["squad_delta_2627"]["defense"] = -d["fio_delta_att"] * 0.85
            d["roma_delta_att"] = _draw(rng, *ROMA_DELTA_ATT)
            ctx["teams"]["Roma"]["squad_delta_2627"]["attack"] = d["roma_delta_att"]

            d["fio_ritorno_scale"] = _draw(rng, *FIO_RITORNO_SCALE)
            h2 = ctx["teams"]["Fiorentina"]["recent_split"]["second_half"]
            h2["goals_for"] *= d["fio_ritorno_scale"]
            h2["goals_against"] /= d["fio_ritorno_scale"]

            fx = ratings.fixture_lambdas(ctx, "Roma", "Fiorentina")
            p_model = dc.outcome_probs(dc.score_matrix(fx.lam_home, fx.lam_away,
                                                       rho=d["RHO"]))
            p_mkt = mk.devig_shin(odds)
            p_fused = mk.log_pool(p_model, p_mkt, d["MARKET_WEIGHT"])

            samples.append({
                "p_home": p_fused["home"], "p_draw": p_fused["draw"],
                "p_away": p_fused["away"],
                "p_model_home": p_model["home"], "p_model_away": p_model["away"],
                "lam_h": fx.lam_home, "lam_a": fx.lam_away,
                "total_goals": fx.lam_home + fx.lam_away,
                "ev_home": p_fused["home"] * odds["home"] - 1.0,
                "ev_draw": p_fused["draw"] * odds["draw"] - 1.0,
                "ev_away": p_fused["away"] * odds["away"] - 1.0,
            })
            draws.append(d)
    finally:
        for k, v in originals.items():
            setattr(ratings, k, v)
        mk.MARKET_WEIGHT = orig_mw

    S = {k: np.array([s[k] for s in samples]) for k in samples[0]}
    D = {k: np.array([d[k] for d in draws]) for k in draws[0]}

    def q(a):
        return {"p05": float(np.percentile(a, 5)), "median": float(np.median(a)),
                "p95": float(np.percentile(a, 95)), "mean": float(a.mean()),
                "sd": float(a.std())}

    # first-order variance attribution: squared correlation of each input with
    # the output, normalised. Crude next to a full Sobol decomposition, but the
    # inputs are drawn independently, so it ranks them honestly.
    target = S["p_home"]
    contrib = {}
    for k, v in D.items():
        if v.std() < 1e-12:
            continue
        r = float(np.corrcoef(v, target)[0, 1])
        contrib[k] = r ** 2
    tot = sum(contrib.values()) or 1.0
    attribution = sorted(({"input": k, "share_of_variance": v / tot,
                           "correlation": float(np.corrcoef(D[k], target)[0, 1])}
                          for k, v in contrib.items()),
                         key=lambda r: -r["share_of_variance"])

    # decision stability
    ev_positive = {k: float((S[f"ev_{k}"] > 0).mean()) for k in ("home", "draw", "away")}
    ev_meaningful = {k: float((S[f"ev_{k}"] > 0.05).mean()) for k in ("home", "draw", "away")}
    roma_favourite = float((S["p_home"] > S["p_draw"]) .mean() * (S["p_home"] > S["p_away"]).mean())

    # Is the "edge" real, or is it just me distrusting the market?
    # EV is measured against the market's own prices, so as MARKET_WEIGHT -> 1
    # the EV must go to zero BY CONSTRUCTION. If positive EV only survives at
    # low market weight, then the edge is not a finding about the match - it is
    # a restatement of how much I chose to disagree with the bookmaker.
    mw = D["MARKET_WEIGHT"]
    bands = []
    for lo, hi in ((0.40, 0.50), (0.50, 0.60), (0.60, 0.70), (0.70, 0.80)):
        sel = (mw >= lo) & (mw < hi)
        if sel.sum() < 30:
            continue
        bands.append({
            "market_weight": f"{lo:.2f}-{hi:.2f}",
            "n": int(sel.sum()),
            "mean_ev_draw": float(S["ev_draw"][sel].mean()),
            "mean_ev_away": float(S["ev_away"][sel].mean()),
            "p_ev_positive_draw": float((S["ev_draw"][sel] > 0).mean()),
            "p_ev_positive_away": float((S["ev_away"][sel] > 0).mean()),
        })
    # The right test is a SIGN FLIP across the range, not an arbitrary pair of
    # probability thresholds. If mean EV is positive when I half-trust the
    # market and negative when I mostly trust it, then the edge is not a
    # property of the match - it is a property of my scepticism.
    def _flips(key):
        vals = [b[key] for b in bands]
        return len(vals) >= 2 and vals[0] > 0 and vals[-1] < 0

    edge_is_artefact = _flips("mean_ev_draw") or _flips("mean_ev_away")

    verdict = _verdict(S, ev_positive, ev_meaningful)

    out = {
        "n_draws": n,
        "distributions": {k: q(S[k]) for k in
                          ("p_home", "p_draw", "p_away", "p_model_home",
                           "total_goals", "ev_home", "ev_draw", "ev_away")},
        "variance_attribution": attribution,
        "decision_stability": {
            "p_ev_positive": ev_positive,
            "p_ev_above_5pct": ev_meaningful,
            "p_roma_remains_favourite": roma_favourite,
            "p_model_disagrees_with_market_on_fiorentina": float(
                (S["p_model_away"] > 0.143).mean()),
        },
        "market_weight_conditioning": {
            "bands": bands,
            "edge_is_an_artefact_of_market_weight": edge_is_artefact,
            "_note": ("EV e misurato contro le quote del mercato, quindi tende a zero "
                      "per costruzione quando il peso del mercato tende a 1. Se l'EV "
                      "positivo sopravvive solo a peso basso, non e una scoperta sulla "
                      "partita: e la misura di quanto ho scelto di non fidarmi del banco."),
        },
        "verdict": verdict,
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "selfaudit.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    return out


def _verdict(S, ev_positive, ev_meaningful) -> dict:
    """Turn the distributions into a stated decision, with its own confidence."""
    best = max(ev_positive, key=ev_positive.get)
    stability = ev_positive[best]
    strong = ev_meaningful[best]

    if strong > 0.60:
        action = "SCOMMESSA CON VALORE"
        reason = (f"l'EV su '{best}' supera il 5% in oltre il 60% dello spazio "
                  "dei parametri plausibili")
    elif stability > 0.85:
        action = "VALORE MARGINALE, NON SUFFICIENTE"
        reason = (f"'{best}' ha EV positivo nell'{stability:.0%} dei casi ma quasi mai "
                  "oltre il 5%: il margine e piu piccolo dell'incertezza del modello")
    else:
        action = "NESSUNA SCOMMESSA"
        reason = (f"la selezione migliore ('{best}') resta in profitto solo nel "
                  f"{stability:.0%} dello spazio dei parametri: e una monetina")

    return {
        "action": action,
        "best_selection": best,
        "stability": stability,
        "reason": reason,
        "p_home_range_90pct": [float(np.percentile(S["p_home"], 5)),
                               float(np.percentile(S["p_home"], 95))],
        "headline_vs_uncertainty": (
            "La forchetta al 90% su P(vittoria Roma) e larga "
            f"{(np.percentile(S['p_home'], 95) - np.percentile(S['p_home'], 5)) * 100:.1f} "
            "punti percentuali. Qualsiasi lettura che si fermi al numero singolo "
            "sta buttando via questa informazione."),
    }


if __name__ == "__main__":
    r = audit()
    d = r["distributions"]
    print(f"AUDIT su {r['n_draws']} estrazioni dello spazio dei parametri\n")
    print("P(vittoria Roma)   mediana %.1f%%   intervallo 90%%  %.1f%% - %.1f%%"
          % (d["p_home"]["median"] * 100, d["p_home"]["p05"] * 100, d["p_home"]["p95"] * 100))
    print("P(pareggio)        mediana %.1f%%" % (d["p_draw"]["median"] * 100))
    print("P(vittoria Fiore.) mediana %.1f%%   intervallo 90%%  %.1f%% - %.1f%%"
          % (d["p_away"]["median"] * 100, d["p_away"]["p05"] * 100, d["p_away"]["p95"] * 100))
    print("Gol totali attesi  mediana %.2f    intervallo 90%%  %.2f - %.2f\n"
          % (d["total_goals"]["median"], d["total_goals"]["p05"], d["total_goals"]["p95"]))

    print("DA DOVE VIENE L'INCERTEZZA (quota della varianza)")
    for a in r["variance_attribution"][:8]:
        print("  %-38s %5.1f%%" % (a["input"], a["share_of_variance"] * 100))

    print("\nSTABILITA DELLA DECISIONE")
    for k, v in r["decision_stability"]["p_ev_positive"].items():
        print("  EV positivo su %-6s %5.1f%% delle estrazioni" % (k, v * 100))

    v = r["verdict"]
    print(f"\nVERDETTO: {v['action']}\n  {v['reason']}\n  {v['headline_vs_uncertainty']}")
