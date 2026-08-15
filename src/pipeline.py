"""End-to-end forecast pipeline. Writes results/predictions.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import dixon_coles as dc
import duels
import market as mk
import ml
import ratings
import simulate as sim

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"

HOME, AWAY = "Roma", "Fiorentina"


def run(n_sims: int = 200_000, seed: int = 42, train_ml: bool = True) -> dict:
    ctx = ratings.load_context()

    # ---- 1. analytical layer -------------------------------------------
    fx = ratings.fixture_lambdas(ctx, HOME, AWAY)
    m_model = dc.score_matrix(fx.lam_home, fx.lam_away)
    p_model = dc.outcome_probs(m_model)

    # ---- 2. market layer -----------------------------------------------
    odds = ctx["market"]["decimal_odds"]
    p_mkt_prop = mk.devig_proportional(odds)
    p_mkt_shin = mk.devig_shin(odds)
    lam_mkt_h, lam_mkt_a = mk.solve_lambdas_for_probs(p_mkt_shin)

    # ---- 3. fusion ------------------------------------------------------
    p_fused = mk.log_pool(p_model, p_mkt_shin, mk.MARKET_WEIGHT)
    # translate the fused 1X2 back into lambdas so every derived market
    # (totals, BTTS, correct score) is consistent with the fused view
    lam_f_h, lam_f_a = mk.solve_lambdas_for_probs(p_fused,
                                                  lam0=fx.lam_home, mu0=fx.lam_away)
    m_fused = dc.score_matrix(lam_f_h, lam_f_a)

    # ---- 4. Monte Carlo with parameter uncertainty -----------------------
    mc = sim.simulate(lam_f_h, lam_f_a, n=n_sims, seed=seed,
                      extra_sigma=ratings.MATCHDAY1_EXTRA_DISPERSION)

    # ---- 5. ML layer -----------------------------------------------------
    ml_block = {"enabled": train_ml}
    if train_ml:
        df = ml.generate_synthetic_league(n_seasons=20, seed=seed)
        trained = ml.train_and_evaluate(df, seed=seed)
        rh = fx.breakdown["home_rating"]
        ra = fx.breakdown["away_rating"]
        ml_pred = ml.predict_fixture(
            trained["models"], rh["attack"], rh["defense"],
            ra["attack"], ra["defense"], home_adv=1.0, rest_diff=0.0, matchday=1)
        ml_block.update({
            "training_rows": int(len(df)),
            "cv_report": trained["report"],
            "fixture_prediction": ml_pred,
            "disagreement_vs_analytical": {
                k: float(ml_pred["ensemble_mean"][k] - p_model[k])
                for k in ("home", "draw", "away")
            },
        })

    # ---- 5b. player-vs-player layer --------------------------------------
    duel_block = duels.run(lam_f_h, lam_f_a, n=400_000, seed=seed + 1)

    # ---- 6. derived markets ---------------------------------------------
    derived = {
        "totals": {**dc.totals(m_fused, 1.5), **dc.totals(m_fused, 2.5),
                   **dc.totals(m_fused, 3.5)},
        "btts": dc.btts(m_fused),
        "clean_sheets": dc.clean_sheets(m_fused),
        "asian_handicap": {
            "home_-0.5": dc.asian_handicap(m_fused, -0.5),
            "home_-1.0": dc.asian_handicap(m_fused, -1.0),
            "home_-1.5": dc.asian_handicap(m_fused, -1.5),
        },
        "top_scorelines": dc.top_scorelines(m_fused, 12),
        "double_chance": {
            "1X": p_fused["home"] + p_fused["draw"],
            "12": p_fused["home"] + p_fused["away"],
            "X2": p_fused["draw"] + p_fused["away"],
        },
    }

    out = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fixture": {
            "home": HOME, "away": AWAY,
            "competition": ctx["_meta"]["competition"],
            "kickoff": ctx["_meta"]["kickoff_local"],
            "venue": ctx["_meta"]["venue"],
        },
        "lambdas": {
            "model": {"home": fx.lam_home, "away": fx.lam_away},
            "market_implied": {"home": lam_mkt_h, "away": lam_mkt_a},
            "fused": {"home": lam_f_h, "away": lam_f_a},
        },
        "ratings_breakdown": fx.breakdown,
        "probabilities": {
            "model_only": p_model,
            "market_proportional": p_mkt_prop,
            "market_shin": p_mkt_shin,
            "fused_FINAL": p_fused,
            "monte_carlo": mc["outcome"],
        },
        "monte_carlo": {k: v for k, v in mc.items() if k != "scorers"},
        "scorers": mc["scorers"],
        "derived_markets": derived,
        "score_matrix_fused": m_fused[:7, :7].tolist(),
        "ml": ml_block,
        "duels": {
            "pairs_evaluated": duel_block["duel_matrix"]["pairs_evaluated"],
            "pairs_that_meet": duel_block["duel_matrix"]["pairs_that_actually_meet"],
            "top_duels": duel_block["duel_matrix"]["duels"][:14],
            "zones": duel_block["zones"],
        },
        "stories": duel_block["stories"],
        "value_bets": mk.edge_table(p_fused, odds),
        "config": {
            "shrink": ratings.SHRINK,
            "recency_weight": ratings.RECENCY_WEIGHT,
            "recency_weight_dixon_coles_decay_equivalent":
                ratings.recency_weight_from_decay(),
            "market_weight": mk.MARKET_WEIGHT,
            "rho": dc.RHO,
            "lambda_sigma": sim.LAMBDA_SIGMA,
            "matchday1_extra_dispersion": ratings.MATCHDAY1_EXTRA_DISPERSION,
            "n_sims": n_sims, "seed": seed,
        },
        "known_unknowns": ctx["known_unknowns"],
    }

    RESULTS.mkdir(exist_ok=True)
    with open(RESULTS / "predictions.json", "w", encoding="utf-8") as fh:
        json.dump(out, fh, indent=2, ensure_ascii=False)
    return out


def sensitivity(param_grid: dict | None = None) -> list[dict]:
    """How much does each knob actually move P(Roma win)? Anything that moves
    it <1pp is decoration; anything >5pp needs a real source behind it."""
    ctx = ratings.load_context()
    rows = []
    base_fx = ratings.fixture_lambdas(ctx, HOME, AWAY)
    base_p = dc.outcome_probs(dc.score_matrix(base_fx.lam_home, base_fx.lam_away))

    grid = param_grid or {
        "SHRINK": [0.55, 0.72, 0.90],
        "H2H_WEIGHT": [0.0, 0.05, 0.15],
        "MATCHDAY1_GOAL_FACTOR": [0.93, 0.97, 1.00],
        "NEW_MANAGER_DISCOUNT": [0.30, 0.55, 0.85],
        "RECENCY_WEIGHT": [0.0, 0.40, 0.75],
    }
    for name, values in grid.items():
        original = getattr(ratings, name)
        for v in values:
            setattr(ratings, name, v)
            fx = ratings.fixture_lambdas(ctx, HOME, AWAY)
            p = dc.outcome_probs(dc.score_matrix(fx.lam_home, fx.lam_away))
            rows.append({
                "param": name, "value": v,
                "p_home": p["home"], "p_draw": p["draw"], "p_away": p["away"],
                "delta_p_home_pp": (p["home"] - base_p["home"]) * 100,
            })
        setattr(ratings, name, original)

    # also vary Fiorentina's squad delta, the single biggest unknown
    for d in (-0.05, 0.0, 0.10, 0.20):
        ctx2 = ratings.load_context()
        ctx2["teams"]["Fiorentina"]["squad_delta_2627"]["attack"] = d
        ctx2["teams"]["Fiorentina"]["squad_delta_2627"]["defense"] = -d
        fx = ratings.fixture_lambdas(ctx2, HOME, AWAY)
        p = dc.outcome_probs(dc.score_matrix(fx.lam_home, fx.lam_away))
        rows.append({
            "param": "fiorentina_squad_delta", "value": d,
            "p_home": p["home"], "p_draw": p["draw"], "p_away": p["away"],
            "delta_p_home_pp": (p["home"] - base_p["home"]) * 100,
        })
    return rows


if __name__ == "__main__":
    res = run()
    print(json.dumps(res["probabilities"], indent=2))
