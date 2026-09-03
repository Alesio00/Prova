"""Il segnale del run 008 regge fuori dal suo campione?

Il run 008 ha misurato un vantaggio del +7,36% confrontando il prezzo di un
book lento con quello di Pinnacle, su 3.163 partite di Premier League
2012-2020 piu' una stagione di Serie A. E ha nominato quattro rischi. Tre
sono affermazioni empiriche, e questo modulo le testa su dati che il run 008
non aveva: 26.054 partite, 7 campionati, fino alla stagione in corso.

Il disegno e' pre-registrato in RESULTS.md § "Run 009 — PRE-REGISTRAZIONE",
committato prima che questo file girasse la prima volta.

LA MACCHINA STATISTICA E' QUELLA DEL RUN 008, DELIBERATAMENTE
------------------------------------------------------------
De-vig proporzionale, contrasto edge-positivo contro edge-negativo, decili,
regressione P&L su edge, bootstrap. Identici. Se cambiassi anche il metodo,
una differenza nei risultati non direbbe se e' cambiato il mondo o il codice.

DUE COSE SONO NUOVE, ED ENTRAMBE POSSONO SOLO PEGGIORARE IL RISULTATO
---------------------------------------------------------------------
1. ACCOPPIAMENTO CHIUSURA-CHIUSURA. Il run 008 confrontava le quote di
   apertura assumendo che fossero contemporanee, e lo dichiarava come
   rischio. Le quote di chiusura sono campionate tutte allo stesso istante
   definito - il calcio d'inizio - quindi l'assunzione di simultaneita'
   regge molto meglio. Ed e' anche il caso piu' ostile: la linea di chiusura
   e' la piu' efficiente, quindi e' li' che un edge finto sparisce.

2. BOOTSTRAP A GRAPPOLO SULLE PARTITE. Sei selezioni sulla stessa partita
   non sono sei osservazioni indipendenti: condividono l'esito. Il run 008
   le trattava come indipendenti, il che STRINGE gli intervalli di confidenza
   piu' del dovuto. Qui si ricampionano le partite, non le selezioni.
   L'intervallo che ne esce e' quello onesto.

IL DIVIETO DI LOOKAHEAD
-----------------------
Mai soft in apertura contro sharp in chiusura. Sarebbe usare un prezzo
futuro per giudicarne uno passato, e produrrebbe un edge inesistente.
`_cols()` costruisce i due accoppiamenti separatamente e `run()` lo verifica
con un assert.
"""

from __future__ import annotations

import json
import re
from math import erfc, sqrt
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache" / "felipedds-football-data-co-uk"
RESULTS = ROOT / "results"

LEGS = ["H", "D", "A"]

# Identica al run 008, e non e' un caso: cambiare l'insieme dei book
# renderebbe i due risultati non confrontabili. I book assenti da un file
# vengono semplicemente saltati.
SOFT = ["B365", "BW", "IW", "LB", "WH", "VC"]
MIN_SOFT = 3          # con meno di tre bersagli il confronto non ha senso
MIN_SOFT_C = 1        # Argentina/Brasile: B365 e' l'UNICO soft disponibile,
                      # quindi e' pre-specificato per costruzione - non c'e'
                      # nessuna selezione possibile, e nessuna multiplicita'

SHARP = "PS"          # Pinnacle
EXCHANGE = "BFE"      # Betfair Exchange - il candidato sostituto

EUROPE = ["E0", "I1", "SP1", "D1", "F1"]
RECENT = ["2021", "2122", "2223", "2324", "2425", "2526"]
OLD = ["1819", "1920"]

STRATA = {
    "A_fuori_tempo":       dict(divs=EUROPE, seasons=RECENT,
                                desc="5 leghe europee, 2020/21-2025/26 - mai usate"),
    "B_fuori_lega":        dict(divs=["I1", "SP1", "D1", "F1"], seasons=OLD,
                                desc="Italia/Spagna/Germania/Francia 2018-2020 - leghe nuove, epoca vecchia"),
    "C_fuori_continente":  dict(divs=["ARG", "BRA"], seasons=None,
                                desc="Argentina + Brasile - solo chiusura, solo B365"),
    "D_sovrapposizione":   dict(divs=["E0"], seasons=OLD,
                                desc="EPL 2018-2020 - DENTRO il run 008: controllo di continuita', non un test"),
}


# ---------------------------------------------------------------- dati ----

def _cols(pairing: str, book: str) -> list[str]:
    """Colonne di un book per un accoppiamento.

    apertura: B365H  B365D  B365A        chiusura: B365CH  B365CD  B365CA
    Le due famiglie non si mescolano mai: vedi il divieto di lookahead.
    """
    assert pairing in ("apertura", "chiusura")
    suf = "" if pairing == "apertura" else "C"
    return [f"{book}{suf}{l}" for l in LEGS]


def load() -> pd.DataFrame:
    """Tutti i file della cache, con schema normalizzato e strato assegnato."""
    if not CACHE.exists():
        raise SystemExit("cache assente: esegui prima  python3 src/fetchdata.py")

    frames = []
    for f in sorted(CACHE.rglob("*.csv")):
        m = re.match(r"(\d{4})_([A-Z0-9]+)\.csv$", f.name)
        extra = re.match(r"(ARG|BRA)\.csv$", f.name)
        if m:
            season, div = m.group(1), m.group(2)
        elif extra:
            season, div = None, extra.group(1)
        else:
            continue

        x = pd.read_csv(f, encoding="latin-1", on_bad_lines="skip",
                        low_memory=False)
        x.columns = [c.strip().lstrip("﻿") for c in x.columns]

        # I file Argentina/Brasile usano nomi diversi per le stesse cose.
        x = x.rename(columns={"Home": "HomeTeam", "Away": "AwayTeam",
                              "Res": "FTR", "HG": "FTHG", "AG": "FTAG"})
        if "FTR" not in x.columns or "Date" not in x.columns:
            continue

        # Argentina/Brasile portano la stagione in colonna; le usiamo tutte.
        seas = season if season else x.get("Season", pd.Series("?", index=x.index)).astype(str)
        frames.append(x.assign(Div=div, Season=seas, src=f.name))

    d = pd.concat(frames, ignore_index=True)
    d = d.assign(y=d.FTR.map({"H": 0, "D": 1, "A": 2})).dropna(subset=["y"])
    d = d.astype({"y": int})

    # Una partita puo' comparire in due file (non dovrebbe, ma il run 008 ha
    # imparato a sue spese che i mirror si sovrappongono).
    d = d.drop_duplicates(subset=["Date", "HomeTeam", "AwayTeam", "Div"],
                          keep="first").reset_index(drop=True)
    # match_id serve al bootstrap a grappolo: identifica la partita, non la riga
    return d.assign(match_id=np.arange(len(d))).copy()


def stratum(d: pd.DataFrame, name: str) -> pd.DataFrame:
    s = STRATA[name]
    m = d.Div.isin(s["divs"])
    if s["seasons"] is not None:
        m &= d.Season.isin(s["seasons"])
    return d[m].copy()


# --------------------------------------------------------- statistica ----

def devig(o: np.ndarray) -> np.ndarray:
    """De-vig proporzionale. Identico al run 008."""
    r = 1.0 / o
    return r / r.sum(axis=1, keepdims=True)


def _ll(P: np.ndarray, y: np.ndarray) -> float:
    return float(-np.log(np.clip(P[np.arange(len(y)), y], 1e-15, 1)).mean())


def _p(t: float) -> float:
    return float(erfc(abs(t) / sqrt(2)))


def _stat(pnl: np.ndarray) -> dict:
    if len(pnl) < 2:
        return {"n": int(len(pnl))}
    roi = float(pnl.mean())
    se = float(pnl.std(ddof=1) / np.sqrt(len(pnl)))
    t = roi / se if se > 0 else 0.0
    return {"n": int(len(pnl)), "roi": roi, "roi_stderr": se,
            "t_stat": float(t), "p_value": _p(t)}


def _numeric(d: pd.DataFrame, cols: list[str]) -> np.ndarray | None:
    if not set(cols).issubset(d.columns):
        return None
    v = d[cols].apply(pd.to_numeric, errors="coerce").values.astype(float)
    return v


def h0(d: pd.DataFrame, pairing: str, sharp: str, books: list[str]) -> dict:
    """Chi e' davvero il piu' affilato - misurato sullo STESSO insieme di partite.

    IL BUG CHE QUESTA FUNZIONE CORREGGE (trovato al primo giro del run 009).
    La prima versione calcolava il log loss di ogni book sulle righe in cui
    QUEL book aveva una quota valida. Ma la copertura cambia moltissimo da
    book a book:

      - `BFE` (Betfair Exchange) esiste solo dal 2024/25: 3.397 partite su
        10.734 nello strato A. Confrontato cosi', risultava il piu' affilato
        di tutti - ma stava giocando su un terzo dei dati, e su quello piu'
        recente.
      - I file 2018/19 non hanno NESSUNA colonna di chiusura per i book soft,
        solo per Pinnacle. Nello strato D il log loss di chiusura di Pinnacle
        veniva da 760 partite e quello dei soft da 380 diverse: il margine
        risultante (+0.041) era una differenza di campione, non di bravura.

    Confrontare log loss su insiemi di partite diversi non misura niente. Qui
    il confronto e' sull'INTERSEZIONE - le partite in cui tutti hanno un
    prezzo - e viene riportata anche la copertura di ciascuno, cosi' che si
    veda subito quanto costa l'intersezione.
    """
    cand = [sharp] + books + [EXCHANGE]
    O, cov = {}, {}
    for b in cand:
        Ob = _numeric(d, _cols(pairing, b))
        if Ob is None:
            continue
        m = np.isfinite(Ob).all(axis=1) & (Ob > 1.0).all(axis=1)
        if m.sum() > 200:
            O[b] = (Ob, m)
            cov[b] = int(m.sum())
    if sharp not in O:
        return {"H0": {"reason": f"{sharp} assente"}}

    common = np.ones(len(d), bool)
    for b in O:
        common &= O[b][1]
    y = d.y.values

    def _lls(mask):
        return {b: _ll(devig(O[b][0][mask]), y[mask]) for b in O}

    out = {"H0_coverage": cov, "H0_n_common": int(common.sum())}
    if common.sum() > 200:
        ll = _lls(common)
        out["H0_log_loss_common"] = ll
        out["H0_overround_common"] = {
            b: float((1.0 / O[b][0][common]).sum(axis=1).mean() - 1) for b in O}
        soft = {k: v for k, v in ll.items() if k in books}
        out["H0_sharpest"] = min(ll, key=ll.get)
        out["H0_premise_holds"] = bool(soft and ll[sharp] < min(soft.values()))
        out["H0_margin_vs_best_soft"] = float(min(soft.values()) - ll[sharp]) if soft else None
    else:
        # Nessuna partita ha tutti i book: si confronta a coppie con lo sharp,
        # che e' il confronto che conta davvero.
        pair = {}
        for b in O:
            if b == sharp:
                continue
            m = O[sharp][1] & O[b][1]
            if m.sum() > 200:
                pair[b] = {"n": int(m.sum()),
                           "ll_sharp": _ll(devig(O[sharp][0][m]), y[m]),
                           "ll_book": _ll(devig(O[b][0][m]), y[m])}
        out["H0_pairwise_vs_sharp"] = pair
        soft_beats = [v for k, v in pair.items()
                      if k in books and v["ll_book"] < v["ll_sharp"]]
        out["H0_premise_holds"] = bool(pair) and not soft_beats
        out["H0_sharpest"] = sharp if out["H0_premise_holds"] else "vedi H0_pairwise_vs_sharp"
        out["H0_margin_vs_best_soft"] = (
            float(min(v["ll_book"] - v["ll_sharp"] for k, v in pair.items() if k in books))
            if any(k in books for k in pair) else None)
    return out


def build_bets(d: pd.DataFrame, pairing: str, sharp: str,
               min_soft: int) -> tuple[pd.DataFrame, dict]:
    """Una riga per (partita, book, esito), con edge e P&L.

    Il P&L e' quello di una puntata da 1 unita': quota-1 se vince, -1 se perde.
    """
    sharp_cols = _cols(pairing, sharp)
    O_sharp = _numeric(d, sharp_cols)
    if O_sharp is None:
        return pd.DataFrame(), {"reason": f"{sharp} assente per {pairing}"}

    ok = np.isfinite(O_sharp).all(axis=1) & (O_sharp > 1.0).all(axis=1)
    d = d[ok].copy()
    P = devig(O_sharp[ok])
    y = d.y.values

    books = [b for b in SOFT if set(_cols(pairing, b)).issubset(d.columns)]
    if len(books) < min_soft:
        return pd.DataFrame(), {"reason": f"solo {len(books)} book soft, ne servono {min_soft}"}

    recs = []
    for b in books:
        Ob = _numeric(d, _cols(pairing, b))
        for k in range(3):
            m = np.isfinite(Ob[:, k]) & (Ob[:, k] > 1.0)
            if not m.any():
                continue
            recs.append(pd.DataFrame({
                "match_id": d.match_id.values[m], "book": b, "leg": LEGS[k],
                "odds": Ob[m, k], "p_sharp": P[m, k],
                "won": (y[m] == k).astype(int),
                "edge": Ob[m, k] * P[m, k] - 1.0,
                "Div": d.Div.values[m], "Season": d.Season.values[m],
            }))
    if not recs:
        return pd.DataFrame(), {"reason": "nessuna selezione"}
    bets = pd.concat(recs, ignore_index=True)
    bets["pnl"] = np.where(bets.won == 1, bets.odds - 1.0, -1.0)

    meta = {"n_matches": int(len(d)), "books": books, "sharp": sharp,
            "pairing": pairing} | h0(d, pairing, sharp, books)
    return bets, meta


def _cluster_bootstrap(bets: pd.DataFrame, n: int = 2000,
                       seed: int = 0) -> dict:
    """Ricampiona le PARTITE, non le selezioni.

    Sei selezioni sulla stessa partita condividono l'esito: trattarle come
    indipendenti stringe gli intervalli piu' del dovuto. Questo e' il conto
    onesto, e da' quasi sempre un intervallo piu' largo di quello del run 008.
    """
    rng = np.random.default_rng(seed)
    ids = bets.match_id.values
    uniq = np.unique(ids)
    order = np.argsort(ids, kind="stable")
    ids_sorted = ids[order]
    pnl_sorted = bets.pnl.values[order]
    edge_sorted = bets.edge.values[order]
    start = np.searchsorted(ids_sorted, uniq, side="left")
    stop = np.searchsorted(ids_sorted, uniq, side="right")

    roi_b, diff_b = [], []
    for _ in range(n):
        pick = rng.integers(0, len(uniq), len(uniq))
        idx = np.concatenate([np.arange(start[i], stop[i]) for i in pick])
        e, p = edge_sorted[idx], pnl_sorted[idx]
        pos, neg = p[e > 0], p[e <= 0]
        if len(pos) > 50:
            roi_b.append(pos.mean())
            if len(neg) > 50:
                diff_b.append(pos.mean() - neg.mean())
    out = {"n_resamples": len(roi_b)}
    if roi_b:
        a = np.array(roi_b)
        out |= {"roi_mean": float(a.mean()),
                "roi_ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
                "prob_roi_positive": float((a > 0).mean())}
    if diff_b:
        b = np.array(diff_b)
        out |= {"contrast_mean_pp": float(b.mean() * 100),
                "contrast_ci95_pp": [float(np.percentile(b, 2.5) * 100),
                                     float(np.percentile(b, 97.5) * 100)],
                "prob_contrast_positive": float((b > 0).mean())}
    return out


def _naive_bootstrap(bets: pd.DataFrame, n: int = 2000, seed: int = 0) -> dict:
    """Il bootstrap del run 008: ricampiona le SELEZIONI come se fossero
    indipendenti. Serve solo per misurare di quanto sbagliava."""
    rng = np.random.default_rng(seed)
    e, p = bets.edge.values, bets.pnl.values
    roi = []
    for _ in range(n):
        i = rng.integers(0, len(e), len(e))
        g = p[i][e[i] > 0]
        if len(g) > 50:
            roi.append(g.mean())
    if not roi:
        return {}
    a = np.array(roi)
    return {"roi_mean": float(a.mean()),
            "roi_ci95": [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))],
            "prob_roi_positive": float((a > 0).mean())}


def analyse(bets: pd.DataFrame) -> dict:
    """Contrasto, soglie, decili, regressione. Stessa forma del run 008."""
    out: dict = {"n_selections": int(len(bets))}
    pos = bets[bets.edge > 0].pnl.values
    neg = bets[bets.edge <= 0].pnl.values
    if len(pos) < 50 or len(neg) < 50:
        out["reason"] = "troppe poche selezioni per il contrasto"
        return out

    diff = float(pos.mean() - neg.mean())
    se_d = float(np.sqrt(pos.var(ddof=1) / len(pos) + neg.var(ddof=1) / len(neg)))
    t_d = diff / se_d if se_d > 0 else 0.0
    out["contrast"] = {
        "roi_all": float(bets.pnl.mean()),
        "roi_edge_positive": float(pos.mean()), "n_positive": int(len(pos)),
        "roi_edge_negative": float(neg.mean()), "n_negative": int(len(neg)),
        "difference_pp": diff * 100, "t_stat": float(t_d), "p_value": _p(t_d),
    }
    out["H1_primary"] = _stat(pos)

    out["by_threshold"] = []
    for th in [0.0, 0.01, 0.02, 0.03, 0.05]:
        g = bets[bets.edge > th]
        s = _stat(g.pnl.values) | {"threshold": th}
        if len(g):
            s["mean_edge"] = float(g.edge.mean())
        out["by_threshold"].append(s)

    b2 = bets.copy()
    b2["q"] = pd.qcut(b2.edge, 10, labels=False, duplicates="drop")
    dec = [{"decile": int(q) + 1, "n": int(len(g)),
            "mean_edge": float(g.edge.mean()), "roi": float(g.pnl.mean())}
           for q, g in b2.groupby("q")]
    out["deciles"] = dec
    r = [x["roi"] for x in dec]
    out["decile_rank_corr"] = float(np.corrcoef(range(len(r)), r)[0, 1]) if len(r) > 2 else None

    # Regressione P&L ~ edge, con errori standard a grappolo sulle partite.
    x, yv = bets.edge.values, bets.pnl.values
    X = np.c_[np.ones(len(x)), x]
    beta, *_ = np.linalg.lstsq(X, yv, rcond=None)
    resid = yv - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    meat = np.zeros((2, 2))
    dfm = pd.DataFrame({"m": bets.match_id.values, "r": resid,
                        "x0": X[:, 0], "x1": X[:, 1]})
    g = dfm.groupby("m").apply(
        lambda t: np.array([(t.x0 * t.r).sum(), (t.x1 * t.r).sum()]),
        include_groups=False)
    S = np.stack(g.values)
    meat = S.T @ S
    cov_cl = XtX_inv @ meat @ XtX_inv
    out["regression"] = {
        "intercept": float(beta[0]),
        "intercept_se_cluster": float(np.sqrt(cov_cl[0, 0])),
        "slope": float(beta[1]),
        "slope_se_cluster": float(np.sqrt(cov_cl[1, 1])),
        "slope_t_cluster": float(beta[1] / np.sqrt(cov_cl[1, 1])),
        "_lettura": ("pendenza > 0 = l'edge stimato e' informativo; "
                     "intercetta ~ 0 = la linea de-viggata del riferimento non e' distorta"),
    }
    out["bootstrap_cluster"] = _cluster_bootstrap(bets)
    out["bootstrap_naive"] = _naive_bootstrap(bets)
    # Quanto costava trattare come indipendenti selezioni della stessa partita?
    cl, na = out["bootstrap_cluster"].get("roi_ci95"), out["bootstrap_naive"].get("roi_ci95")
    if cl and na and (na[1] - na[0]) > 0:
        out["cluster_widening_factor"] = float((cl[1] - cl[0]) / (na[1] - na[0]))

    out["by_season"] = []
    for (dv, se), g in bets[bets.edge > 0].groupby(["Div", "Season"]):
        s = _stat(g.pnl.values) | {"div": dv, "season": se}
        if s.get("n", 0) > 100:
            out["by_season"].append(s)
    out["by_season"].sort(key=lambda s: -s.get("roi", -9))

    # Il contrasto stagione per stagione: se il segnale e' morto, questa
    # tabella dice QUANDO. Un ROI medio nasconde una decadenza; questa no.
    out["contrast_by_season"] = []
    for se, g in bets.groupby("Season"):
        pos, neg = g[g.edge > 0].pnl.values, g[g.edge <= 0].pnl.values
        if len(pos) < 100 or len(neg) < 100:
            continue
        dd = float(pos.mean() - neg.mean())
        sd = float(np.sqrt(pos.var(ddof=1) / len(pos) + neg.var(ddof=1) / len(neg)))
        t = dd / sd if sd > 0 else 0.0
        out["contrast_by_season"].append({
            "season": str(se), "n_matches": int(g.match_id.nunique()),
            "n_positive": int(len(pos)), "roi_positive": float(pos.mean()),
            "difference_pp": dd * 100, "t_stat": float(t), "p_value": _p(t)})
    out["contrast_by_season"].sort(key=lambda x: x["season"])
    return out


# ------------------------------------------------------------- driver ----

def run() -> dict:
    d = load()
    out: dict = {"n_matches_total": int(len(d)),
                 "inventory": {k: int(v) for k, v in
                               d.groupby(["Div"]).size().items()}}

    # Il divieto di lookahead, verificato invece che dichiarato.
    for b in SOFT + [SHARP, EXCHANGE]:
        assert not (set(_cols("apertura", b)) & set(_cols("chiusura", b))), \
            "accoppiamento contaminato: apertura e chiusura condividono una colonna"

    out["strata"] = {}
    for name in STRATA:
        s = stratum(d, name)
        entry = {"desc": STRATA[name]["desc"], "n_matches": int(len(s)),
                 "divs": sorted(s.Div.unique().tolist()),
                 "seasons": sorted(s.Season.unique().tolist())}
        min_soft = MIN_SOFT_C if name.startswith("C") else MIN_SOFT
        for pairing in ("apertura", "chiusura"):
            bets, meta = build_bets(s, pairing, SHARP, min_soft)
            if bets.empty:
                entry[pairing] = meta
                continue
            entry[pairing] = meta | analyse(bets)
        out["strata"][name] = entry

    # Q4 - il riferimento affilato esiste ancora, e chi lo sostituisce?
    ov = d[d.Div.isin(EUROPE) & d.Season.isin(["2425", "2526"])]
    q4: dict = {"n_matches": int(len(ov)),
                "_domanda": "Betfair Exchange regge come riferimento al posto di Pinnacle?"}
    for pairing in ("apertura", "chiusura"):
        for ref, tag in ((SHARP, "pinnacle"), (EXCHANGE, "betfair_exchange")):
            bets, meta = build_bets(ov, pairing, ref, MIN_SOFT)
            if bets.empty:
                q4[f"{tag}_{pairing}"] = meta
                continue
            q4[f"{tag}_{pairing}"] = meta | analyse(bets)
    out["Q4_sostituzione_riferimento"] = q4
    out["esplorativo"] = exploratory(d)
    return out


def exploratory(d: pd.DataFrame) -> dict:
    """POST-HOC. Le domande qui sotto sono nate GUARDANDO i risultati.

    Non sono test: sono descrizioni. Il punto di taglio fra le due ere e' stato
    scelto dopo aver visto la tabella per stagione, quindi qualunque p-value
    calcolato qui e' ottimistico per costruzione e non va usato per decidere
    niente. Serve a formulare l'ipotesi che un run futuro potra' pre-registrare
    su dati che ancora non esistono - le stagioni 2026/27 in avanti.
    """
    out: dict = {"_avvertenza": ("post-hoc: taglio scelto dopo aver visto i dati. "
                                 "Descrittivo, non confermativo.")}
    A = stratum(d, "A_fuori_tempo")

    for pairing in ("apertura", "chiusura"):
        bets, _ = build_bets(A, pairing, SHARP, MIN_SOFT)
        if bets.empty:
            continue
        blk: dict = {}

        # (a) le due ere che la tabella per stagione suggerisce
        for era, seasons in (("2020-2023", ["2021", "2122", "2223"]),
                             ("2023-2026", ["2324", "2425", "2526"])):
            g = bets[bets.Season.isin(seasons)]
            pos, neg = g[g.edge > 0], g[g.edge <= 0]
            if len(pos) < 100 or len(neg) < 100:
                continue
            dd = float(pos.pnl.mean() - neg.pnl.mean())
            sd = float(np.sqrt(pos.pnl.var(ddof=1) / len(pos)
                               + neg.pnl.var(ddof=1) / len(neg)))
            blk[era] = {
                "n_matches": int(g.match_id.nunique()),
                "roi_edge_positive": float(pos.pnl.mean()),
                "difference_pp": dd * 100,
                "t_stat": float(dd / sd) if sd > 0 else 0.0,
                "bootstrap": _cluster_bootstrap(g, n=1000),
            }

        # (b) chi guida il risultato: un book solo o tutti?
        blk["per_book"] = []
        for b, g in bets.groupby("book"):
            pos = g[g.edge > 0]
            if len(pos) > 200:
                blk["per_book"].append(_stat(pos.pnl.values) | {"book": b})
        blk["per_book"].sort(key=lambda x: -x["roi"])

        # (c) togliendo la stagione peggiore, il quadro cambia?
        worst = min(bets.Season.unique(),
                    key=lambda se: bets[(bets.Season == se) & (bets.edge > 0)].pnl.mean()
                    if (bets[(bets.Season == se) & (bets.edge > 0)].shape[0] > 100) else 9)
        g = bets[bets.Season != worst]
        pos, neg = g[g.edge > 0], g[g.edge <= 0]
        dd = float(pos.pnl.mean() - neg.pnl.mean())
        sd = float(np.sqrt(pos.pnl.var(ddof=1) / len(pos) + neg.pnl.var(ddof=1) / len(neg)))
        blk["senza_stagione_peggiore"] = {
            "esclusa": str(worst), "roi_edge_positive": float(pos.pnl.mean()),
            "difference_pp": dd * 100, "t_stat": float(dd / sd) if sd > 0 else 0.0}

        out[pairing] = blk

    # LA DIAGNOSTICA CHE SPIEGA TUTTO IL RESTO.
    # Il run 007 aveva isolato il meccanismo: conta l'affilatezza del
    # riferimento, non il modello ne' la quantita' di dati. Quindi la domanda
    # giusta non e' "perche' la strategia ha smesso di funzionare" ma "il
    # riferimento e' ancora affilato?". Overround e margine di log loss di
    # Pinnacle, stagione per stagione, rispondono direttamente.
    out["premessa_per_stagione"] = []
    for se in RECENT:
        g = A[A.Season == se]
        books = [b for b in SOFT if set(_cols("chiusura", b)).issubset(g.columns)]
        h = h0(g, "chiusura", SHARP, books)
        ll, ovr = h.get("H0_log_loss_common"), h.get("H0_overround_common")
        if not ll:
            continue
        soft = {k: v for k, v in ll.items() if k in SOFT}
        if not soft:
            continue
        best = min(soft, key=soft.get)
        out["premessa_per_stagione"].append({
            "season": se, "n": h["H0_n_common"],
            "ll_sharp": ll[SHARP], "best_soft": best, "ll_best_soft": soft[best],
            "margin": soft[best] - ll[SHARP],
            "overround_sharp": ovr[SHARP],
            "overround_soft_mean": float(np.mean([v for k, v in ovr.items() if k in SOFT])),
            "sharp_still_sharpest": bool(soft[best] > ll[SHARP]),
        })
    return out


def _h0_print(e: dict) -> None:
    """H0 stampato con la copertura accanto, perche' e' li' che si nasconde l'errore."""
    holds = e.get("H0_premise_holds")
    mar = e.get("H0_margin_vs_best_soft")
    print(f"   H0 premessa {'REGGE' if holds else 'CADE'}"
          f"   margine sul miglior soft {mar:+.5f}" if mar is not None
          else f"   H0 premessa {'REGGE' if holds else 'CADE'}")
    ll = e.get("H0_log_loss_common")
    if ll:
        print(f"      su {e['H0_n_common']:,} partite comuni a tutti: "
              + "  ".join(f"{k}={v:.4f}" for k, v in sorted(ll.items(), key=lambda kv: kv[1])))
    pw = e.get("H0_pairwise_vs_sharp")
    if pw:
        print("      nessuna partita ha tutti i book; confronto a coppie con il riferimento:")
        for b, v in sorted(pw.items(), key=lambda kv: kv[1]["ll_book"] - kv[1]["ll_sharp"]):
            print(f"        vs {b:<6} n={v['n']:>6,}  {e['sharp']}={v['ll_sharp']:.4f}"
                  f"  {b}={v['ll_book']:.4f}  delta {v['ll_book']-v['ll_sharp']:+.4f}")
    cov = e.get("H0_coverage", {})
    if cov:
        print("      copertura: " + "  ".join(f"{k}={v:,}" for k, v in sorted(cov.items())))


def report(r: dict) -> None:
    print(f"partite caricate: {r['n_matches_total']:,}")
    print("  " + "  ".join(f"{k}={v:,}" for k, v in sorted(r["inventory"].items())))

    for name, s in r["strata"].items():
        print("\n" + "=" * 74)
        print(f"{name}   {s['desc']}")
        print(f"partite {s['n_matches']:,}   div {','.join(s['divs'])}   "
              f"stagioni {len(s['seasons'])}")
        print("=" * 74)
        for pairing in ("apertura", "chiusura"):
            e = s.get(pairing, {})
            print(f"\n-- accoppiamento {pairing} --")
            if "reason" in e and "contrast" not in e:
                print(f"   non calcolabile: {e['reason']}")
                continue
            print(f"   book: {','.join(e['books'])}   selezioni {e['n_selections']:,}")
            _h0_print(e)
            c = e.get("contrast")
            if not c:
                continue
            print(f"   CONTRASTO  edge>0 {c['roi_edge_positive']*100:+.2f}% (n={c['n_positive']:,})"
                  f"   edge<=0 {c['roi_edge_negative']*100:+.2f}%"
                  f"   diff {c['difference_pp']:+.2f} pp   t={c['t_stat']:+.2f}  p={c['p_value']:.2e}")
            g = e["regression"]
            print(f"   regressione  pendenza {g['slope']:+.3f} (t grappolo {g['slope_t_cluster']:+.2f})"
                  f"   intercetta {g['intercept']:+.4f} (se {g['intercept_se_cluster']:.4f})")
            b, nb = e.get("bootstrap_cluster", {}), e.get("bootstrap_naive", {})
            if "roi_ci95" in b:
                print(f"   bootstrap a grappolo  ROI {b['roi_mean']*100:+.2f}%"
                      f"   IC95 [{b['roi_ci95'][0]*100:+.2f}%, {b['roi_ci95'][1]*100:+.2f}%]"
                      f"   P(ROI>0) {b['prob_roi_positive']*100:.1f}%")
            if "roi_ci95" in nb:
                print(f"   (metodo run 008, non raggruppato: IC95 "
                      f"[{nb['roi_ci95'][0]*100:+.2f}%, {nb['roi_ci95'][1]*100:+.2f}%]"
                      f"  -> raggruppare allarga di {e.get('cluster_widening_factor', float('nan')):.2f}x)")
            print("   decili: " + " ".join(f"{x['roi']*100:+.1f}" for x in e["deciles"])
                  + f"   (corr {e['decile_rank_corr']:+.2f})")
            cs = e.get("contrast_by_season") or []
            if len(cs) > 1:
                print("   contrasto per stagione:")
                for x in cs:
                    print(f"      {x['season']:<6} n={x['n_matches']:>5,}"
                          f"  edge>0 {x['roi_positive']*100:+7.2f}%"
                          f"  diff {x['difference_pp']:+7.2f} pp  t={x['t_stat']:+5.2f}")

    print("\n" + "=" * 74)
    print("Q4  il riferimento affilato: Pinnacle contro Betfair Exchange")
    print("=" * 74)
    q = r["Q4_sostituzione_riferimento"]
    print(f"overlap 2024/25-2025/26: {q['n_matches']:,} partite")
    for k, v in q.items():
        if not isinstance(v, dict) or "contrast" not in v:
            continue
        c = v["contrast"]
        ll = (v.get("H0_log_loss_common") or {}).get(v["sharp"])
        print(f"  {k:<28} ll={ll:.4f}" if ll else f"  {k:<28}         ", end="")
        print(f"  n={v['n_matches']:>5,}  contrasto {c['difference_pp']:+6.2f} pp"
              f"  p={c['p_value']:.1e}  ROI edge>0 {c['roi_edge_positive']*100:+.2f}%")

    ex = r.get("esplorativo", {})
    if ex:
        print("\n" + "=" * 74)
        print("ESPLORATIVO (post-hoc, descrittivo - NON un test)")
        print("=" * 74)
        for pairing in ("apertura", "chiusura"):
            blk = ex.get(pairing)
            if not blk:
                continue
            print(f"\n-- {pairing} --")
            for era in ("2020-2023", "2023-2026"):
                v = blk.get(era)
                if not v:
                    continue
                b = v["bootstrap"]
                ci = b.get("roi_ci95", [float('nan')] * 2)
                print(f"   {era}  n={v['n_matches']:>5,}  ROI edge>0 {v['roi_edge_positive']*100:+7.2f}%"
                      f"  contrasto {v['difference_pp']:+7.2f} pp  t={v['t_stat']:+5.2f}"
                      f"  IC95 [{ci[0]*100:+.1f}%, {ci[1]*100:+.1f}%]")
            w = blk.get("senza_stagione_peggiore", {})
            if w:
                print(f"   senza la stagione peggiore ({w['esclusa']}): "
                      f"ROI {w['roi_edge_positive']*100:+.2f}%  contrasto {w['difference_pp']:+.2f} pp"
                      f"  t={w['t_stat']:+.2f}")
            print("   per book: " + "  ".join(
                f"{x['book']}={x['roi']*100:+.1f}%(n={x['n']:,})" for x in blk.get("per_book", [])))

        ps = ex.get("premessa_per_stagione") or []
        if ps:
            print("\n-- il riferimento e' ancora affilato? (chiusura, strato A) --")
            print(f"   {'stag':<6}{'n':>6}{'ll Pinn':>10}{'miglior soft':>16}"
                  f"{'margine':>10}{'ovr Pinn':>11}{'ovr soft':>10}")
            for x in ps:
                print(f"   {x['season']:<6}{x['n']:>6}{x['ll_sharp']:>10.4f}"
                      f"{x['best_soft'] + ' ' + format(x['ll_best_soft'], '.4f'):>16}"
                      f"{x['margin']:>+10.4f}{x['overround_sharp']*100:>10.2f}%"
                      f"{x['overround_soft_mean']*100:>9.2f}%"
                      + ("" if x["sharp_still_sharpest"] else "   <-- battuto da un soft"))


if __name__ == "__main__":
    res = run()
    report(res)
    RESULTS.mkdir(exist_ok=True)
    (RESULTS / "validate_oos.json").write_text(
        json.dumps(res, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
    print(f"\nscritto {RESULTS / 'validate_oos.json'}")
