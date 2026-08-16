"""Due domande che restano dopo un backtest negativo.

Il modello da solo perde contro il mercato (log loss 0.9725 contro 0.9511) e
qualunque filtro "EV positivo" perde soldi in modo statisticamente
significativo. Restano due possibilita, e vanno testate entrambe prima di
chiudere, perche sono le uniche in cui un modello battuto puo comunque valere:

1. IL MODELLO AGGIUNGE INFORMAZIONE AL MERCATO?
   Un previsore peggiore puo comunque migliorare uno migliore, se sbaglia in
   modo diverso. Si fonde con log-pooling a peso variabile e si guarda se
   esiste un peso w > 0 che batte il mercato puro. Se il minimo cade a w = 0,
   il modello non aggiunge NIENTE e va usato solo come racconto, mai come
   prezzo. E' il test decisivo del progetto, ed e' anche la giustificazione
   diretta del parametro MARKET_WEIGHT scelto a mano.

2. C'E' UN VANTAGGIO SU OVER/UNDER invece che su 1X2?
   L'ipotesi emersa dal council: le quote over/under non sono mai entrate nel
   modello, quindi li l'opinione sarebbe genuinamente indipendente. Qui c'e il
   dato per verificarlo invece di ipotizzarlo.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

import backtest_odds as B
import dixon_coles as dc
from backtest import _ll

RESULTS = Path(__file__).resolve().parent.parent / "results"


def blend_curve(bt: pd.DataFrame) -> dict:
    """Log loss al variare del peso dato al modello nella fusione."""
    y = bt.result.values
    P = bt[["p_home", "p_draw", "p_away"]].values
    Q = bt[["m_home", "m_draw", "m_away"]].values
    eps = 1e-12
    out = []
    for w in np.round(np.arange(0.0, 1.01, 0.05), 2):
        F = np.exp(w * np.log(P + eps) + (1 - w) * np.log(Q + eps))
        F /= F.sum(axis=1, keepdims=True)
        out.append({"model_weight": float(w), "log_loss": _ll(F, y)})
    best = min(out, key=lambda r: r["log_loss"])
    market_only = next(r for r in out if r["model_weight"] == 0.0)
    return {
        "curve": out,
        "best_weight": best["model_weight"],
        "best_log_loss": best["log_loss"],
        "market_only_log_loss": market_only["log_loss"],
        "improvement_over_market": market_only["log_loss"] - best["log_loss"],
        "model_adds_information": best["model_weight"] > 0.0,
    }


def over_under(bt: pd.DataFrame, edge_min: float = 0.05) -> dict:
    """Il modello ha un vantaggio sul totale gol?"""
    d = bt.dropna(subset=["o_over25", "o_under25"]).copy()
    if d.empty:
        return {"n": 0, "note": "nessuna quota over/under nel campione"}

    y = (d.total > 2.5).astype(int).values
    p = d.p_over25.values
    raw = np.c_[1 / d.o_over25.values, 1 / d.o_under25.values]
    m_over = raw[:, 0] / raw.sum(axis=1)

    def ll_bin(pp):
        pp = np.clip(pp, 1e-15, 1 - 1e-15)
        return float(-(y * np.log(pp) + (1 - y) * np.log(1 - pp)).mean())

    bets, pnl = 0, []
    for i in range(len(d)):
        for side, prob, odds in (("over", p[i], d.o_over25.values[i]),
                                 ("under", 1 - p[i], d.o_under25.values[i])):
            if not np.isfinite(odds) or odds <= 1:
                continue
            if prob * odds - 1.0 < edge_min:
                continue
            won = (y[i] == 1) if side == "over" else (y[i] == 0)
            bets += 1
            pnl.append(odds - 1.0 if won else -1.0)

    res = {"n": int(len(d)),
           "model_log_loss": ll_bin(p), "market_log_loss": ll_bin(m_over),
           "model_minus_market": ll_bin(p) - ll_bin(m_over),
           "base_rate_over25": float(y.mean()),
           "model_mean_p_over": float(p.mean()),
           "n_bets": bets}
    if pnl:
        a = np.array(pnl)
        se = a.std(ddof=1) / np.sqrt(len(a))
        res.update({"roi": float(a.mean()), "roi_stderr": float(se),
                    "t_stat": float(a.mean() / se) if se > 0 else 0.0})
    return res


def by_favourite(bt: pd.DataFrame) -> list[dict]:
    """Dove il modello sbaglia di piu: per fascia di quota del favorito."""
    d = bt.copy()
    d["fav_odds"] = d[["o_home", "o_draw", "o_away"]].min(axis=1)
    bands = [(1.0, 1.5), (1.5, 2.0), (2.0, 2.8), (2.8, 99)]
    out = []
    for lo, hi in bands:
        g = d[(d.fav_odds >= lo) & (d.fav_odds < hi)]
        if len(g) < 50:
            continue
        y = g.result.values
        P = g[["p_home", "p_draw", "p_away"]].values
        Q = g[["m_home", "m_draw", "m_away"]].values
        out.append({"fascia_quota_favorito": f"{lo}-{hi}", "n": int(len(g)),
                    "model_log_loss": _ll(P, y), "market_log_loss": _ll(Q, y),
                    "gap": _ll(P, y) - _ll(Q, y)})
    return out


if __name__ == "__main__":
    df = B.load()
    p = json.load(open(RESULTS / "backtest_odds.json"))["tuned_params"]
    bt = B.walk_forward(df, xi=p["xi"], shrink=p["shrink"], rho=p["rho"])
    test = bt[bt.date >= B.TRAIN_END]

    out = {
        "n_test": int(len(test)),
        "blend": blend_curve(test),
        "over_under": over_under(test),
        "by_favourite_band": by_favourite(test),
    }
    (RESULTS / "backtest_blend.json").write_text(
        json.dumps(out, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    b = out["blend"]
    print("=== IL MODELLO AGGIUNGE INFORMAZIONE AL MERCATO? ===")
    print(f"peso ottimo del modello : {b['best_weight']}")
    print(f"log loss solo mercato   : {b['market_only_log_loss']:.5f}")
    print(f"log loss fusione ottima : {b['best_log_loss']:.5f}")
    print(f"miglioramento           : {b['improvement_over_market']:+.5f}")
    print(f"=> {'SI, aggiunge qualcosa' if b['model_adds_information'] else 'NO, peso ottimo zero'}")
    print()
    print("=== OVER/UNDER 2.5 ===")
    print(json.dumps(out["over_under"], indent=2, ensure_ascii=False))
    print()
    print("=== DOVE SBAGLIA DI PIU ===")
    for r in out["by_favourite_band"]:
        print("  favorito %s  n=%4d  modello %.4f  mercato %.4f  gap %+.4f"
              % (r["fascia_quota_favorito"], r["n"], r["model_log_loss"],
                 r["market_log_loss"], r["gap"]))
