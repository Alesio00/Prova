"""Strategia della dispersione: nessun modello, solo prezzi.

ORIGINE. Il council ha convergito da tre lenti indipendenti sulla stessa idea.
Il First Principles l'ha formulata in modo eseguibile: una scommessa e' un
contratto comprato a un prezzo, e l'EV e' (probabilita vera x prezzo) - 1. Il
progetto ha speso quattro giorni sul primo fattore e ha perso il 16.7%. Il
secondo fattore - comprare al prezzo migliore invece che al medio - ha prodotto
+9.9 punti di ROI senza toccare una riga del modello.

Quindi si abbandona la previsione e si testa il prezzo:

    p_consenso = de-vig delle quote MEDIE dei bookmaker
    edge       = quota_MASSIMA x p_consenso - 1
    si scommette dove edge > soglia

Zero Dixon-Coles, zero rating, zero Monte Carlo. Il consenso e' la stima
migliore disponibile (l'ha appena dimostrato il backtest), e il book che offre
il prezzo piu alto e' quello che si discosta dal consenso.

IPOTESI PRE-REGISTRATE, scritte prima di eseguire
-------------------------------------------------
H1 (primaria) Su tutte le divisioni, l'edge medio realizzato di questa
              strategia a soglia 0 e' > 0.
              Un solo test, nessuna correzione necessaria.

H2 (secondaria, esplorativa) L'edge e' piu grande dove il mercato e' meno
              liquido: campionati minori, quote alte, dispersione ampia.
              Molti test => controllo del False Discovery Rate.

CRITERIO DI MORTE, dichiarato prima (First Principles)
    Se l'edge medio sulla quota massima e' <= 0 dopo il de-vig, qui non c'e'
    business e il progetto e' intellettuale, non finanziario.

AVVERTENZE CHE NON VANNO DIMENTICATE
------------------------------------
1. MOLTEPLICITA (Contrarian). 15 divisioni x 3 mercati x 5 soglie sono ~200
   test: a caso una decina risultera "profittevole" a p<0.05. Ogni risultato
   stratificato passa per Benjamini-Hochberg, e il test primario resta uno solo.

2. BIAS MECCANICO DEL MASSIMO. La quota massima e' il massimo di N estrazioni
   rumorose: e' alta anche se nessun book sbaglia davvero. E la media INCLUDE
   il massimo. Quindi "max > media" e' in parte aritmetica, non segnale. Per
   questo si misura l'edge REALIZZATO sui risultati veri, mai la differenza
   fra i due prezzi.

3. MONETIZZABILITA (Contrarian). I book che offrono la quota massima sono
   spesso quelli che limitano i vincenti, con tetti bassi sulle leghe minori.
   Un edge misurato qui non e' automaticamente un edge incassabile. Questo
   codice misura l'esistenza, non l'accessibilita.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path("/tmp/claude-0/-home-user-Prova/f7c0655e-f766-5448-b6c5-7a7f2f6688ec"
            "/scratchpad/odds-Club-Football-Match-Data-2000-2025/data/Matches.csv")
RESULTS = Path(__file__).resolve().parent.parent / "results"

MARKETS = {
    "1X2": (["OddHome", "OddDraw", "OddAway"], ["MaxHome", "MaxDraw", "MaxAway"]),
    "OU25": (["Over25", "Under25"], ["MaxOver25", "MaxUnder25"]),
}


def load_all() -> pd.DataFrame:
    d = pd.read_csv(DATA, low_memory=False)
    d["date"] = pd.to_datetime(d.MatchDate, errors="coerce")
    d = d.dropna(subset=["date", "FTHome", "FTAway"])
    d["gh"] = d.FTHome.astype(int)
    d["ga"] = d.FTAway.astype(int)
    d["res3"] = np.where(d.gh > d.ga, 0, np.where(d.gh == d.ga, 1, 2))
    d["over"] = (d.gh + d.ga > 2.5).astype(int)
    return d.sort_values("date").reset_index(drop=True)


def build_bets(d: pd.DataFrame, market: str) -> pd.DataFrame:
    """Una riga per selezione giocabile, con edge stimato e P&L realizzato."""
    avg_cols, max_cols = MARKETS[market]
    sub = d.dropna(subset=avg_cols + max_cols).copy()
    if sub.empty:
        return pd.DataFrame()

    A = sub[avg_cols].values.astype(float)
    M = sub[max_cols].values.astype(float)
    ok = (A > 1.0).all(axis=1) & (M > 1.0).all(axis=1) & (M >= A - 1e-9).all(axis=1)
    sub, A, M = sub[ok], A[ok], M[ok]
    if len(sub) == 0:
        return pd.DataFrame()

    raw = 1.0 / A
    overround = raw.sum(axis=1)
    p_cons = raw / overround[:, None]          # consenso de-viggato

    if market == "1X2":
        y = np.eye(3, dtype=int)[sub.res3.values]
    else:
        y = np.c_[sub.over.values, 1 - sub.over.values]

    rows = []
    n_sel = A.shape[1]
    for k in range(n_sel):
        rows.append(pd.DataFrame({
            "date": sub.date.values, "division": sub.Division.values,
            "market": market, "leg": k,
            "p_cons": p_cons[:, k], "odds_max": M[:, k], "odds_avg": A[:, k],
            "won": y[:, k],
            "edge": M[:, k] * p_cons[:, k] - 1.0,
            "dispersion": M[:, k] / A[:, k] - 1.0,
            "overround": overround - 1.0,
        }))
    b = pd.concat(rows, ignore_index=True)
    b["pnl"] = np.where(b.won == 1, b.odds_max - 1.0, -1.0)
    return b


def summarise(b: pd.DataFrame, label: str = "") -> dict:
    if len(b) == 0:
        return {"label": label, "n": 0}
    pnl = b.pnl.values
    roi = float(pnl.mean())
    se = float(pnl.std(ddof=1) / np.sqrt(len(pnl))) if len(pnl) > 1 else float("nan")
    t = roi / se if se and se > 0 else 0.0
    from math import erfc, sqrt
    p = erfc(abs(t) / sqrt(2))                  # bilaterale, normale
    return {"label": label, "n": int(len(pnl)), "roi": roi, "roi_stderr": se,
            "t_stat": float(t), "p_value": float(p),
            "mean_edge_claimed": float(b.edge.mean()),
            "hit_rate": float(b.won.mean()),
            "mean_odds": float(b.odds_max.mean())}


def benjamini_hochberg(rows: list[dict], alpha: float = 0.05) -> list[dict]:
    """Controllo del False Discovery Rate. Senza questo, su ~200 strati una
    decina di 'scoperte' e' garantita dal caso."""
    valid = [r for r in rows if r.get("n", 0) > 0 and np.isfinite(r.get("p_value", np.nan))]
    valid.sort(key=lambda r: r["p_value"])
    m = len(valid)
    for i, r in enumerate(valid, start=1):
        r["bh_threshold"] = alpha * i / m if m else 0.0
        r["significant_fdr"] = bool(r["p_value"] <= r["bh_threshold"] and r["roi"] > 0)
    # una scoperta e' valida solo se lo e' anche tutto cio che la precede
    passed = False
    for r in reversed(valid):
        if r.get("significant_fdr"):
            passed = True
        r["significant_fdr"] = passed and r["roi"] > 0
    return valid


def run() -> dict:
    d = load_all()
    out: dict = {"n_matches_total": int(len(d)),
                 "divisions": sorted(d.Division.dropna().unique().tolist())}

    allbets = pd.concat([build_bets(d, m) for m in MARKETS], ignore_index=True)
    out["n_selections"] = int(len(allbets))

    # ---- H1: test primario, uno solo, nessuna correzione ----------------
    out["H1_primary"] = summarise(allbets, "tutte le divisioni, tutti i mercati, soglia 0")

    # solo 1X2, per confronto diretto col backtest precedente
    out["H1_1x2_only"] = summarise(allbets[allbets.market == "1X2"], "solo 1X2")

    # ---- H2: esplorativo, con controllo FDR ------------------------------
    strata = []
    for (div, mk_), g in allbets.groupby(["division", "market"]):
        if len(g) < 300:
            continue
        strata.append(summarise(g, f"{div} / {mk_}"))
    for lo, hi in ((1.0, 1.6), (1.6, 2.5), (2.5, 4.0), (4.0, 8.0), (8.0, 1e9)):
        g = allbets[(allbets.odds_max >= lo) & (allbets.odds_max < hi)]
        if len(g) >= 300:
            strata.append(summarise(g, f"quota {lo}-{hi if hi < 1e9 else 'inf'}"))
    for lo, hi in ((0.0, 0.02), (0.02, 0.05), (0.05, 0.10), (0.10, 1.0)):
        g = allbets[(allbets.dispersion >= lo) & (allbets.dispersion < hi)]
        if len(g) >= 300:
            strata.append(summarise(g, f"dispersione {lo:.0%}-{hi:.0%}"))
    for th in (0.0, 0.02, 0.05, 0.10):
        g = allbets[allbets.edge > th]
        if len(g) >= 300:
            strata.append(summarise(g, f"soglia edge >{th:.0%}"))

    out["H2_strata"] = benjamini_hochberg(strata)
    out["n_strata_tested"] = len(strata)
    out["n_significant_after_fdr"] = sum(
        1 for r in out["H2_strata"] if r.get("significant_fdr"))

    # ---- criterio di morte ----------------------------------------------
    h1 = out["H1_primary"]
    out["verdict"] = {
        "H1_roi": h1["roi"],
        "H1_significant": bool(h1["p_value"] < 0.05 and h1["roi"] > 0),
        "death_criterion_met": bool(h1["roi"] <= 0),
        "reading": ("edge medio positivo: la strategia esiste"
                    if h1["roi"] > 0 else
                    "edge medio non positivo: criterio di morte soddisfatto, "
                    "qui non c'e' business"),
    }
    return out


if __name__ == "__main__":
    r = run()
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "strategy_dispersion.json").write_text(
        json.dumps(r, indent=2, ensure_ascii=False, default=str), encoding="utf-8")

    print(f"partite: {r['n_matches_total']:,}   selezioni: {r['n_selections']:,}")
    print(f"divisioni: {len(r['divisions'])}\n")
    for k in ("H1_primary", "H1_1x2_only"):
        s = r[k]
        print(f"{s['label']}")
        print(f"  n={s['n']:,}  ROI {s['roi']*100:+.2f}%  (se {s['roi_stderr']*100:.2f}%)"
              f"  t={s['t_stat']:+.2f}  p={s['p_value']:.2e}")
        print(f"  edge medio DICHIARATO {s['mean_edge_claimed']*100:+.2f}%"
              f"  quota media {s['mean_odds']:.2f}\n")
    print(f"strati testati: {r['n_strata_tested']}   "
          f"significativi dopo FDR: {r['n_significant_after_fdr']}")
    print("\ntop 12 strati per ROI:")
    for s in sorted(r["H2_strata"], key=lambda x: -x["roi"])[:12]:
        flag = "  <== FDR OK" if s.get("significant_fdr") else ""
        print(f"  {s['label']:<28} n={s['n']:>7,}  ROI {s['roi']*100:+7.2f}%"
              f"  t={s['t_stat']:+6.2f}{flag}")
    print(f"\nVERDETTO: {r['verdict']['reading']}")
