"""Backtest con quote reali: train/test separati e la domanda che conta.

Il dataset (Club-Football-Match-Data-2000-2025) ha 9.012 partite di Serie A dal
2000 al 2025 con quote 1X2, over/under 2.5, handicap ed Elo. Con le quote si
puo finalmente rispondere alla domanda che il progetto si porta dietro da
quattro run:

    IL MODELLO BATTE IL MERCATO?

E' una domanda a risposta secca. Se il log loss del modello e' peggiore di
quello delle quote de-viggate, non c'e nessun vantaggio da cercare: qualunque
EV positivo trovato e' rumore o un errore di misura. Nessuna quantita di
tuning cambia questo, e scoprirlo presto vale piu di qualsiasi ottimizzazione.

SPLIT TEMPORALE, MAI CASUALE. Mescolare le partite e poi dividere farebbe
addestrare su partite del futuro rispetto a quelle di test: il modello
imparerebbe la forza delle squadre in stagioni che nel test finge di non
conoscere. Si divide per data e basta.

    train  2000/01 - 2016/17   per tarare xi, shrink, rho
    test   2017/18 - 2024/25   mai guardato durante la taratura
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import dixon_coles as dc
from backtest import _brier, _ll, calibration, ece, fit_ratings

DATA = Path("/tmp/claude-0/-home-user-Prova/f7c0655e-f766-5448-b6c5-7a7f2f6688ec"
            "/scratchpad/odds-Club-Football-Match-Data-2000-2025/data/Matches.csv")
RESULTS = Path(__file__).resolve().parent.parent / "results"

TRAIN_END = "2017-07-01"     # confine train/test, scelto PRIMA di guardare i risultati
MIN_HISTORY = 380


def load(division: str = "I1") -> pd.DataFrame:
    d = pd.read_csv(DATA, low_memory=False)
    d = d[d.Division == division].copy()
    d["date"] = pd.to_datetime(d.MatchDate)
    d = d.rename(columns={"HomeTeam": "home", "AwayTeam": "away",
                          "FTHome": "gh", "FTAway": "ga"})
    d = d.dropna(subset=["gh", "ga", "OddHome", "OddDraw", "OddAway"])
    d["gh"] = d.gh.astype(int); d["ga"] = d.ga.astype(int)
    d["result"] = np.where(d.gh > d.ga, 0, np.where(d.gh == d.ga, 1, 2))
    d["total"] = d.gh + d.ga
    return d.sort_values("date").reset_index(drop=True)


def devig_row(o_h, o_d, o_a) -> tuple[float, float, float]:
    r = np.array([1 / o_h, 1 / o_d, 1 / o_a])
    return tuple(r / r.sum())


def walk_forward(df: pd.DataFrame, xi: float, shrink: float, rho: float,
                 refit_every: int = 10, min_history: int = MIN_HISTORY) -> pd.DataFrame:
    df = df.sort_values("date").reset_index(drop=True)
    rows, att, dfn = [], None, None
    base_h = base_a = 0.0
    last_fit = -10**9

    for i in range(min_history, len(df)):
        m = df.iloc[i]
        if i - last_fit >= refit_every:
            hist = df.iloc[:i]
            hist = hist[hist.date < m.date]
            if len(hist) < min_history:
                continue
            att, dfn, base_h, base_a = fit_ratings(hist, m.date, xi)
            last_fit = i
        if att is None or m.home not in att or m.away not in att:
            continue

        lam = base_h * (1 + (att[m.home] - 1) * shrink) * (1 + (dfn[m.away] - 1) * shrink)
        mu = base_a * (1 + (att[m.away] - 1) * shrink) * (1 + (dfn[m.home] - 1) * shrink)
        M = dc.score_matrix(lam, mu, rho=rho)
        p = dc.outcome_probs(M)
        mh, md, ma = devig_row(m.OddHome, m.OddDraw, m.OddAway)
        n = M.shape[0]
        idx = np.add.outer(np.arange(n), np.arange(n))

        rows.append({
            "date": m.date, "home": m.home, "away": m.away,
            "result": m.result, "total": m.total,
            "p_home": p["home"], "p_draw": p["draw"], "p_away": p["away"],
            "m_home": mh, "m_draw": md, "m_away": ma,
            "o_home": m.OddHome, "o_draw": m.OddDraw, "o_away": m.OddAway,
            "max_home": m.get("MaxHome", m.OddHome),
            "max_draw": m.get("MaxDraw", m.OddDraw),
            "max_away": m.get("MaxAway", m.OddAway),
            "p_over25": float(M[idx > 2.5].sum()),
            "o_over25": m.get("Over25", np.nan),
            "o_under25": m.get("Under25", np.nan),
            "lam": lam, "mu": mu,
        })
    return pd.DataFrame(rows)


def compare(bt: pd.DataFrame) -> dict:
    y = bt.result.values
    P = bt[["p_home", "p_draw", "p_away"]].values
    Q = bt[["m_home", "m_draw", "m_away"]].values
    n = len(y)
    prior = np.bincount(y, minlength=3) / n
    return {
        "n": int(n),
        "model_log_loss": _ll(P, y),
        "market_log_loss": _ll(Q, y),
        "prior_log_loss": _ll(np.tile(prior, (n, 1)), y),
        "model_brier": _brier(P, y),
        "market_brier": _brier(Q, y),
        "model_minus_market": _ll(P, y) - _ll(Q, y),
        "model_accuracy": float((P.argmax(1) == y).mean()),
        "market_accuracy": float((Q.argmax(1) == y).mean()),
    }


def betting_sim(bt: pd.DataFrame, edge_min: float = 0.05, use_max: bool = False,
                stake: float = 1.0) -> dict:
    """Puntata piatta su ogni selezione con EV sopra soglia.

    Piatta e non Kelly di proposito: Kelly amplifica sia il segnale sia
    l'errore di stima, e con un modello non ancora dimostrato calibrato sul
    mercato amplificherebbe soprattutto il secondo.
    """
    cols = ("home", "draw", "away")
    bets, pnl = [], []
    for r in bt.itertuples():
        for k, c in enumerate(cols):
            p = getattr(r, f"p_{c}")
            o = getattr(r, f"max_{c}") if use_max else getattr(r, f"o_{c}")
            if not np.isfinite(o) or o <= 1.0:
                continue
            ev = p * o - 1.0
            if ev < edge_min:
                continue
            won = (r.result == k)
            bets.append({"ev": ev, "odds": o, "won": won})
            pnl.append(stake * (o - 1.0) if won else -stake)

    if not bets:
        return {"n_bets": 0, "note": "nessuna selezione supera la soglia"}
    pnl = np.array(pnl)
    roi = pnl.sum() / (len(pnl) * stake)
    # errore standard del ROI: senza questo un ROI positivo non dice nulla
    se = pnl.std(ddof=1) / np.sqrt(len(pnl)) / stake
    return {
        "n_bets": int(len(pnl)),
        "edge_threshold": edge_min,
        "odds_used": "massima disponibile" if use_max else "media bookmaker",
        "profit_units": float(pnl.sum()),
        "roi": float(roi),
        "roi_stderr": float(se),
        "t_stat": float(roi / se) if se > 0 else 0.0,
        "hit_rate": float(np.mean([b["won"] for b in bets])),
        "mean_odds": float(np.mean([b["odds"] for b in bets])),
        "significant_at_95pct": bool(abs(roi / se) > 1.96) if se > 0 else False,
    }


def tune(train: pd.DataFrame, grid: dict | None = None) -> dict:
    """Taratura SOLO sul training set. Il test non viene toccato."""
    grid = grid or {"xi": [0.002, 0.004, 0.0065, 0.010],
                    "shrink": [0.7, 0.85, 1.0],
                    "rho": [-0.14, -0.10, -0.06]}
    best, results = None, []
    for xi in grid["xi"]:
        for sh in grid["shrink"]:
            bt = walk_forward(train, xi=xi, shrink=sh, rho=-0.10)
            if bt.empty:
                continue
            y = bt.result.values
            for rho in grid["rho"]:
                # rho non richiede un nuovo fit: si riproietta la matrice
                P = np.array([list(dc.outcome_probs(
                    dc.score_matrix(r.lam, r.mu, rho=rho)).values())
                    for r in bt.itertuples()])
                ll = _ll(P, y)
                results.append({"xi": xi, "shrink": sh, "rho": rho, "log_loss": ll})
                if best is None or ll < best["log_loss"]:
                    best = results[-1]
    return {"best": best, "grid_results": sorted(results, key=lambda r: r["log_loss"])}


if __name__ == "__main__":
    df = load()
    train = df[df.date < TRAIN_END]
    test = df[df.date >= TRAIN_END]
    print(f"train {len(train)} partite ({train.date.min().date()} -> {train.date.max().date()})")
    print(f"test  {len(test)} partite ({test.date.min().date()} -> {test.date.max().date()})")

    print("\n--- taratura sul training set ---")
    t = tune(train)
    b = t["best"]
    print(f"migliori parametri: xi={b['xi']} shrink={b['shrink']} rho={b['rho']}"
          f"  (log loss train {b['log_loss']:.4f})")

    print("\n--- valutazione sul TEST, mai visto ---")
    bt = walk_forward(df, xi=b["xi"], shrink=b["shrink"], rho=b["rho"])
    bt_test = bt[bt.date >= TRAIN_END]
    cmp_ = compare(bt_test)
    cal = calibration(bt_test)
    out = {
        "split": {"train_end": TRAIN_END, "n_train": int(len(train)),
                  "n_test": int(len(test)), "n_test_predicted": int(len(bt_test))},
        "tuned_params": b,
        "test_metrics": cmp_,
        "test_ece": ece(cal),
        "calibration": cal,
        "betting": {
            "edge_5pct_avg_odds": betting_sim(bt_test, 0.05, use_max=False),
            "edge_10pct_avg_odds": betting_sim(bt_test, 0.10, use_max=False),
            "edge_5pct_best_odds": betting_sim(bt_test, 0.05, use_max=True),
        },
        "grid_top5": t["grid_results"][:5],
    }
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "backtest_odds.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(json.dumps({k: v for k, v in out.items()
                      if k not in ("calibration", "grid_top5")},
                     indent=2, ensure_ascii=False, default=str))
