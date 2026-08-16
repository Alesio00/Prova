"""Sharp contro soft: il metodo professionale, testato per la prima volta.

L'IDEA, che e' diversa da tutto quello provato finora.

Nei quattro run precedenti la "probabilita vera" veniva sempre da me: dal
Dixon-Coles, dai rating, dal consenso di mercato. Sempre battuta.

Qui la probabilita vera viene da un MERCATO SPECIFICO noto per essere il piu
affilato - Pinnacle, che opera a margini bassi, accetta puntate grosse e non
limita i vincenti. Il bersaglio non e' "il mercato" in astratto: e' un
bookmaker specifico che si discosta da Pinnacle sullo stesso evento, allo
stesso momento.

    p_sharp   = de-vig delle quote Pinnacle
    edge_b    = quota_del_book_b x p_sharp - 1
    si punta sul book b dove edge > soglia

E' il metodo documentato in letteratura come l'unico che produce profitto
reale nelle scommesse sportive. Non richiede di prevedere il calcio: richiede
solo che un book sia piu lento di un altro.

IPOTESI PRE-REGISTRATE
----------------------
H0 (premessa) Pinnacle de-viggato ha log loss MINORE dei book soft de-viggati.
              Se questo e' falso, la premessa del metodo cade e il resto non
              va nemmeno interpretato.
H1 (primaria) Puntando sui book soft dove edge > 0, il ROI realizzato e' > 0.
H2 (secondaria) Il ROI cresce con la soglia di edge. E' il test che il modello
              Dixon-Coles ha fallito in modo spettacolare (a soglia piu alta
              perdeva di piu): qui deve andare nella direzione giusta.

LIMITI DA DICHIARARE PRIMA, non dopo
------------------------------------
- Solo Premier League 2012-2016: 1.516 partite. E' un campione PICCOLO
  rispetto ai 230.000 usati finora, quindi la potenza statistica e bassa e un
  risultato nullo non distingue "non c'e' edge" da "non lo vedo".
- La Premier League e' il mercato piu efficiente al mondo. Se un edge esiste,
  qui e' dove e' piu difficile trovarlo.
- Le quote sono quelle pubblicate da football-data, senza timestamp: si assume
  che siano contemporanee, il che e' approssimativamente ma non esattamente
  vero.
- Un edge misurato qui non e' automaticamente incassabile: i book soft che
  sbagliano sono anche quelli che limitano i conti vincenti.
"""

from __future__ import annotations

import glob
import json
import re
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

SCRATCH = Path("/tmp/claude-0/-home-user-Prova/f7c0655e-f766-5448-b6c5-7a7f2f6688ec"
               "/scratchpad")

# Il primo campione (EPL 2012-2016) e' quello su cui l'ipotesi e' stata
# formulata. Tutto il resto e' arrivato DOPO, e viene tenuto separato: e' un
# test fuori campione vero, non un ampliamento del campione di scoperta.
DISCOVERY = [SCRATCH / "fd-RudrakshTuwani-Football-Data-Analysis-and-Prediction"
             / "Datasets"]
HOLDOUT = [SCRATCH / "y-Caff1982-football-predictions" / "data",
           SCRATCH / "y-mellacsi-SerieAStatistics" / "resources",
           SCRATCH / "y-woobe-footballytics" / "data"]
RESULTS = Path(__file__).resolve().parent.parent / "results"

SHARP = "PS"                                  # Pinnacle
SOFT = ["B365", "BW", "IW", "LB", "WH", "VC"]
LEGS = ["H", "D", "A"]


MIN_SOFT = 3   # con meno di tre book soft il confronto non ha abbastanza bersagli


def _read_dirs(dirs) -> pd.DataFrame:
    """Ogni file porta i bookmaker che ha.

    La prima versione pretendeva tutti e sette i book in ogni file e scartava
    silenziosamente le stagioni a cui ne mancava uno solo - buttando via 509
    partite che AVEVANO Pinnacle e a cui mancava soltanto Ladbrokes. Serve
    Pinnacle (senza riferimento affilato non si fa niente) e almeno MIN_SOFT
    book soft; quali siano, cambia da file a file e non importa.
    """
    sharp_cols = [SHARP + l for l in LEGS]
    frames = []
    for dd in dirs:
        for f in sorted(glob.glob(str(dd / "*.csv"))):
            # gli aggregati "joined"/"all_seasons" duplicano le stagioni singole
            if re.search(r"joined|all_seasons|fixtures|Standings|league|EMA|^test",
                         Path(f).name, re.I):
                continue
            try:
                x = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip")
            except Exception:
                continue
            if not set(sharp_cols + ["FTR"]).issubset(x.columns):
                continue
            books = [b for b in SOFT
                     if set(b + l for l in LEGS).issubset(x.columns)]
            if len(books) < MIN_SOFT:
                continue
            cols = sharp_cols + [b + l for b in books for l in LEGS]
            x = x.dropna(subset=cols + ["FTR"])
            num = x[cols].apply(pd.to_numeric, errors="coerce")
            x = x[(num > 1.0).all(axis=1)]
            if not len(x):
                continue
            x = x.copy()
            x["src"] = Path(f).name
            x["books_available"] = ",".join(books)
            # i book assenti restano NaN e vengono saltati a valle
            for b in SOFT:
                for l in LEGS:
                    if b + l not in x.columns:
                        x[b + l] = np.nan
            frames.append(x[["FTR", "Date", "HomeTeam", "AwayTeam", "src",
                             "books_available"] +
                            [c for c in sharp_cols +
                             [b + l for b in SOFT for l in LEGS]]
                            + (["Div"] if "Div" in x.columns else [])])
    if not frames:
        return pd.DataFrame()
    d = pd.concat(frames, ignore_index=True)
    d["y"] = d.FTR.map({"H": 0, "D": 1, "A": 2})
    d = d.dropna(subset=["y"])
    # una partita puo comparire in piu repository: si tiene una sola copia
    key = ["Date", "HomeTeam", "AwayTeam"]
    if set(key).issubset(d.columns):
        d = d.drop_duplicates(subset=key, keep="first")
    return d.reset_index(drop=True)


def load(which: str = "discovery") -> pd.DataFrame:
    if which == "discovery":
        return _read_dirs(DISCOVERY)
    if which == "holdout":
        disc = _read_dirs(DISCOVERY)
        hold = _read_dirs(HOLDOUT)
        if len(disc) and len(hold):
            key = ["Date", "HomeTeam", "AwayTeam"]
            seen = set(map(tuple, disc[key].values))
            hold = hold[[tuple(r) not in seen for r in hold[key].values]]
        return hold.reset_index(drop=True)
    return _read_dirs(DISCOVERY + HOLDOUT)


def devig(o: np.ndarray) -> np.ndarray:
    r = 1.0 / o
    return r / r.sum(axis=1, keepdims=True)


def _ll(P: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.clip(P[np.arange(len(y)), y], 1e-15, 1)).mean())


def _stat(pnl: np.ndarray) -> dict:
    if len(pnl) == 0:
        return {"n": 0}
    roi = float(pnl.mean())
    se = float(pnl.std(ddof=1) / np.sqrt(len(pnl))) if len(pnl) > 1 else float("nan")
    t = roi / se if se and se > 0 else 0.0
    return {"n": int(len(pnl)), "roi": roi, "roi_stderr": se, "t_stat": float(t),
            "p_value": float(erfc(abs(t) / sqrt(2))),
            "profit_units": float(pnl.sum())}


def run(which: str = "discovery") -> dict:
    d = load(which)
    if d.empty:
        return {"n_matches": 0, "sample": which}
    y = d.y.values.astype(int)
    O_sharp = d[[SHARP + l for l in LEGS]].values.astype(float)
    p_sharp = devig(O_sharp)

    out: dict = {"sample": which, "n_matches": int(len(d)),
                 "divisions": sorted(d.Div.dropna().unique().tolist()) if "Div" in d else [],
                 "period": [str(d.Date.iloc[0]), str(d.Date.iloc[-1])],
                 "sharp": SHARP, "soft": SOFT}

    # ---- H0: Pinnacle e' davvero il piu affilato? -----------------------
    ll = {SHARP: _ll(p_sharp, y)}
    for b in SOFT:
        Ob = d[[b + l for l in LEGS]].apply(pd.to_numeric, errors="coerce").values
        m = np.isfinite(Ob).all(axis=1) & (Ob > 1.0).all(axis=1)
        if m.sum() > 200:
            ll[b] = _ll(devig(Ob[m]), y[m])
    best = min(ll, key=ll.get)
    out["H0_log_loss_by_book"] = ll
    out["H0_sharpest_book"] = best
    out["H0_premise_holds"] = bool(best == SHARP)
    out["H0_margin_vs_best_soft"] = float(
        min(v for k, v in ll.items() if k != SHARP) - ll[SHARP])

    # overround medio per book: misura diretta di quanto e' "soft"
    ovr = {}
    for b in [SHARP] + SOFT:
        Ob = d[[b + l for l in LEGS]].apply(pd.to_numeric, errors="coerce").values
        m = np.isfinite(Ob).all(axis=1) & (Ob > 1.0).all(axis=1)
        if m.sum() > 200:
            ovr[b] = float((1.0 / Ob[m]).sum(axis=1).mean() - 1)
    out["overround_by_book"] = ovr

    # ---- H1/H2: la strategia --------------------------------------------
    recs = []
    for b in SOFT:
        Ob = d[[b + l for l in LEGS]].apply(pd.to_numeric, errors="coerce").values
        for k in range(3):
            m = np.isfinite(Ob[:, k]) & (Ob[:, k] > 1.0)
            if not m.any():
                continue
            recs.append(pd.DataFrame({
                "book": b, "leg": LEGS[k], "odds": Ob[m, k],
                "p_sharp": p_sharp[m, k], "won": (y[m] == k).astype(int),
                "edge": Ob[m, k] * p_sharp[m, k] - 1.0,
                "date": d.Date.values[m],
            }))
    bets = pd.concat(recs, ignore_index=True)
    bets["pnl"] = np.where(bets.won == 1, bets.odds - 1.0, -1.0)
    out["n_selections"] = int(len(bets))

    thresholds = [0.0, 0.01, 0.02, 0.03, 0.05]
    out["H1_H2_by_threshold"] = []
    for th in thresholds:
        g = bets[bets.edge > th]
        s = _stat(g.pnl.values)
        s["threshold"] = th
        s["mean_edge_claimed"] = float(g.edge.mean()) if len(g) else None
        s["mean_odds"] = float(g.odds.mean()) if len(g) else None
        out["H1_H2_by_threshold"].append(s)

    prim = next(s for s in out["H1_H2_by_threshold"] if s["threshold"] == 0.0)
    out["H1_primary"] = prim

    # monotonicita: il ROI cresce con la soglia?
    rois = [s["roi"] for s in out["H1_H2_by_threshold"] if s.get("n", 0) > 100]
    out["H2_monotone_increasing"] = bool(
        len(rois) >= 3 and all(rois[i] <= rois[i + 1] + 1e-9 for i in range(len(rois) - 1)))
    out["H2_roi_sequence"] = rois

    # per bookmaker, a soglia 0
    out["by_book"] = []
    for b in SOFT:
        g = bets[(bets.book == b) & (bets.edge > 0)]
        s = _stat(g.pnl.values)
        s["book"] = b
        out["by_book"].append(s)

    # ---- IL TEST DECISIVO: contrasto edge-positivo vs edge-negativo ------
    # Il ROI assoluto confonde due cose: se il segnale contiene informazione, e
    # se il livello supera il margine del book. Il contrasto separa le due.
    # Se l'edge stimato NON contiene informazione, le due popolazioni devono
    # avere lo stesso ROI. E' il test che il Dixon-Coles falliva al contrario.
    pos = bets[bets.edge > 0].pnl.values
    neg = bets[bets.edge <= 0].pnl.values
    diff = float(pos.mean() - neg.mean())
    se_d = float(np.sqrt(pos.var(ddof=1) / len(pos) + neg.var(ddof=1) / len(neg)))
    t_d = diff / se_d if se_d > 0 else 0.0
    out["contrast_test"] = {
        "roi_all_soft": float(bets.pnl.mean()),
        "roi_edge_positive": float(pos.mean()), "n_positive": int(len(pos)),
        "roi_edge_negative": float(neg.mean()), "n_negative": int(len(neg)),
        "difference_pp": diff * 100, "t_stat": float(t_d),
        "p_value": float(erfc(abs(t_d) / sqrt(2))),
        "signal_is_real": bool(diff > 0 and erfc(abs(t_d) / sqrt(2)) < 0.01),
    }

    # monotonicita sui decili dell'intera distribuzione dell'edge, non solo
    # sulle soglie alte dove n e' piccolo e domina il rumore
    b2 = bets.copy()
    b2["q"] = pd.qcut(b2.edge, 10, labels=False, duplicates="drop")
    dec = []
    for q, g in b2.groupby("q"):
        dec.append({"decile": int(q) + 1, "n": int(len(g)),
                    "mean_edge": float(g.edge.mean()),
                    "roi": float(g.pnl.mean()),
                    "t_stat": float(g.pnl.mean() / (g.pnl.std(ddof=1) / np.sqrt(len(g))))})
    rois_dec = [x["roi"] for x in dec]
    out["edge_deciles"] = dec
    out["decile_monotone"] = bool(
        np.corrcoef(range(len(rois_dec)), rois_dec)[0, 1] > 0.8)
    out["edge_pnl_correlation"] = float(np.corrcoef(bets.edge, bets.pnl)[0, 1])

    # ---- POTENZA: regressione e bootstrap --------------------------------
    # Il test diretto usa solo le selezioni con edge>0 (3.665 su 47.754) e
    # butta via il 92% dei dati. La regressione li usa tutti: se l'edge stimato
    # e' informativo, la pendenza dev'essere positiva, e l'intercetta dev'essere
    # ZERO (a edge nullo il rendimento atteso e' nullo, se la linea de-viggata
    # di Pinnacle e' non distorta).
    x = bets.edge.values
    yv = bets.pnl.values
    X = np.c_[np.ones(len(x)), x]
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    cov = (resid @ resid / (len(x) - 2)) * np.linalg.inv(X.T @ X)
    me = float(bets[bets.edge > 0].edge.mean())
    gvec = np.array([1.0, me])
    pred = float(beta[0] + beta[1] * me)
    se_pred = float(np.sqrt(gvec @ cov @ gvec))
    out["regression"] = {
        "intercept": float(beta[0]), "intercept_se": float(np.sqrt(cov[0, 0])),
        "slope": float(beta[1]), "slope_se": float(np.sqrt(cov[1, 1])),
        "slope_t": float(beta[1] / np.sqrt(cov[1, 1])),
        "predicted_roi_at_mean_positive_edge": pred,
        "predicted_roi_se": se_pred,
        "_reading": ("pendenza positiva = l'edge stimato e' informativo; "
                     "intercetta ~0 = la linea Pinnacle de-viggata e' non distorta"),
    }

    rng = np.random.default_rng(0)
    boots = []
    for _ in range(2000):
        idx = rng.integers(0, len(bets), len(bets))
        g = bets.iloc[idx]
        g = g[g.edge > 0]
        if len(g) > 50:
            boots.append(g.pnl.mean())
    if boots:
        ba = np.array(boots)
        out["bootstrap"] = {
            "n_resamples": len(ba), "mean_roi": float(ba.mean()),
            "ci95_low": float(np.percentile(ba, 2.5)),
            "ci95_high": float(np.percentile(ba, 97.5)),
            "prob_roi_positive": float((ba > 0).mean()),
        }

    # ---- verdetto --------------------------------------------------------
    out["verdict"] = {
        "premise_holds": out["H0_premise_holds"],
        "H1_roi": prim.get("roi"),
        "H1_significant_positive": bool(
            prim.get("roi", 0) > 0 and prim.get("p_value", 1) < 0.05),
        "signal_real": out["contrast_test"]["signal_is_real"],
        "reading": (
            "premessa caduta: Pinnacle non e' il piu affilato in questo campione"
            if not out["H0_premise_holds"] else
            "edge positivo e significativo" if (prim.get("roi", 0) > 0 and prim.get("p_value", 1) < 0.05)
            else "edge positivo ma non significativo" if prim.get("roi", 0) > 0
            else "nessun edge"),
    }
    return out


def _print(r):
    print(f"partite {r['n_matches']:,}  ({r['period'][0]} -> {r['period'][1]})")
    print(f"selezioni {r['n_selections']:,}\n")
    print("H0 - chi e' il piu affilato? (log loss, piu basso = meglio)")
    for b, v in sorted(r["H0_log_loss_by_book"].items(), key=lambda kv: kv[1]):
        mark = "  <== sharp" if b == r["sharp"] else ""
        print(f"  {b:<6} {v:.5f}   overround {r['overround_by_book'].get(b, float('nan'))*100:5.2f}%{mark}")
    print(f"  premessa regge: {r['H0_premise_holds']}"
          f"   margine sul miglior soft: {r['H0_margin_vs_best_soft']:+.5f}\n")

    print("H1/H2 - la strategia, per soglia di edge")
    print("  soglia    n      ROI       t      p")
    for s in r["H1_H2_by_threshold"]:
        if not s.get("n"):
            continue
        print(f"  {s['threshold']:>5.0%}  {s['n']:>6,}  {s['roi']*100:+7.2f}%"
              f"  {s['t_stat']:+6.2f}  {s['p_value']:.3f}")
    print(f"\n  ROI crescente con la soglia (H2): {r['H2_monotone_increasing']}")
    print(f"  sequenza: {[round(x*100,2) for x in r['H2_roi_sequence']]}\n")

    print("per bookmaker (soglia 0)")
    for s in sorted(r["by_book"], key=lambda x: -x.get("roi", -9)):
        if s.get("n"):
            print(f"  {s['book']:<6} n={s['n']:>5,}  ROI {s['roi']*100:+6.2f}%  t={s['t_stat']:+5.2f}")
    print(f"\nVERDETTO: {r['verdict']['reading']}")


if __name__ == "__main__":
    all_out = {}
    for which, titolo in (("discovery", "CAMPIONE DI SCOPERTA (EPL 2012-2016)"),
                          ("holdout", "TEST FUORI CAMPIONE (dati trovati dopo)"),
                          ("all", "TUTTO INSIEME")):
        r = run(which)
        all_out[which] = r
        print("=" * 66)
        print(titolo)
        print("=" * 66)
        if not r.get("n_matches"):
            print("nessun dato\n")
            continue
        _print(r)
        print()
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "strategy_sharp_vs_soft.json").write_text(
        json.dumps(all_out, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8")
