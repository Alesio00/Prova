"""Parser per i dati openfootball, e costruzione della tabella di lega reale.

Fino al run 003 tutti i rating venivano da snippet di ricerca: la rete era
bloccata verso i siti di statistiche e l'unico canale erano frammenti di testo.
GitHub pero non era bloccato. openfootball/italy contiene la Serie A partita per
partita dal 2013/14 al 2026/27, ed e' quello che serviva dall'inizio.

Il file ha due formati a seconda della stagione, e vanno gestiti entrambi:

    2013/14 - 2024/25:  Squadra Casa      v Squadra Ospite      2-1 (0-0)
    2025/26 in poi:     Squadra Casa  2-1 (0-0)  Squadra Ospite

I nomi delle squadre cambiano fra stagioni e fra file ("AS Roma", "Roma",
"ACF Fiorentina", "Fiorentina"), quindi vanno normalizzati o meta' dei rating
finiscono su squadre fantasma.
"""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

import pandas as pd

REPO = Path("/tmp/claude-0/-home-user-Prova/f7c0655e-f766-5448-b6c5-7a7f2f6688ec"
            "/scratchpad/italy-openfootball")

# Formato nuovo: "  20:45   AS Roma  1-0 (0-0)  Bologna"
RE_NEW = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s+)?(.+?)\s+(\d+)-(\d+)\s*(?:\([\d-]+\))?\s+(.+?)\s*$")
# Formato vecchio: "    20:30  AC Perugia  v Bologna FC   2-1 (0-0)"
RE_OLD = re.compile(
    r"^\s*(?:\d{1,2}:\d{2}\s+)?(.+?)\s+v\s+(.+?)\s+(\d+)-(\d+)\s*(?:\([\d-]+\))?\s*$")
RE_DATE = re.compile(r"^\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\s+(\w{3})\s+(\d{1,2})"
                     r"(?:\s+(\d{4}))?\s*$")
RE_ROUND = re.compile(r"^\s*▪\s*(?:Matchday|Regular Season\s*-)\s*(\d+)")

MONTHS = {m: i + 1 for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"])}

# I suffissi societari sono rumore: vanno via prima del confronto.
_STRIP = re.compile(
    r"\b(FC|AC|AS|SS|SSC|US|ACF|SSD|Calcio|1909|1913|1907|1919|Milano|CFC|BC|"
    r"SPAL|Srl)\b", re.I)


def canon(name: str) -> str:
    """Nome canonico di una squadra, stabile fra stagioni e fra formati."""
    n = _STRIP.sub(" ", name)
    n = re.sub(r"\s+", " ", n).strip()
    fixes = {
        "Internazionale": "Inter", "Inter Milano": "Inter",
        "Hellas Verona": "Verona", "Verona Hellas": "Verona",
        "Chievo Verona": "Chievo", "Juventus": "Juventus",
        "Napoli": "Napoli", "Roma": "Roma", "Fiorentina": "Fiorentina",
        "Milan": "Milan", "Lazio": "Lazio", "Atalanta": "Atalanta",
    }
    return fixes.get(n, n)


def parse_season(path: Path, season: str) -> list[dict]:
    """Il file non ripete sempre l'anno sulle righe di data: alcune stagioni lo
    scrivono solo la prima volta, altre mai. Si ricava dalla stagione stessa -
    da agosto a dicembre e' l'anno di partenza, da gennaio a luglio il
    successivo. Senza questo, quattro stagioni intere venivano scartate."""
    start_year = int(season.split("-")[0])
    rows, cur_date, cur_round, year = [], None, None, None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if not line.strip() or line.lstrip().startswith(("#", "=", "(")):
            continue

        m = RE_ROUND.match(line)
        if m:
            cur_round = int(m.group(1))
            continue

        m = RE_DATE.match(line)
        if m:
            _, mon, day, yr = m.groups()
            mo = MONTHS[mon]
            year = int(yr) if yr else (start_year if mo >= 7 else start_year + 1)
            cur_date = datetime(year, mo, int(day))
            continue

        # marcatori fra parentesi su riga propria: gia esclusi sopra
        m = RE_OLD.match(line)
        if m:
            h, a, gh, ga = m.group(1), m.group(2), int(m.group(3)), int(m.group(4))
        else:
            m = RE_NEW.match(line)
            if not m:
                continue
            h, gh, ga, a = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)

        h, a = canon(h), canon(a)
        if not h or not a or h == a or len(h) < 3 or len(a) < 3:
            continue
        rows.append({"season": season, "round": cur_round, "date": cur_date,
                     "home": h, "away": a, "gh": gh, "ga": ga})
    return rows


def load_serie_a(repo: Path = REPO, seasons: list[str] | None = None) -> pd.DataFrame:
    """Tutte le partite di Serie A disponibili, ordinate per data."""
    out = []
    for d in sorted(repo.iterdir()):
        if not d.is_dir() or not re.match(r"^\d{4}-\d{2}$", d.name):
            continue
        if seasons and d.name not in seasons:
            continue
        f = d / "1-seriea.txt"
        if f.exists():
            out.extend(parse_season(f, d.name))
    df = pd.DataFrame(out)
    if df.empty:
        return df
    df = df.dropna(subset=["date"]).sort_values("date").reset_index(drop=True)
    df["result"] = (df.gh < df.ga).astype(int) + (df.gh == df.ga).astype(int) * 1
    df["result"] = df.apply(
        lambda r: 0 if r.gh > r.ga else (1 if r.gh == r.ga else 2), axis=1)
    df["total"] = df.gh + df.ga
    return df


def league_table(df: pd.DataFrame, season: str) -> pd.DataFrame:
    """Classifica reale di una stagione, ricostruita dalle partite."""
    s = df[df.season == season]
    teams = sorted(set(s.home) | set(s.away))
    rec = {t: dict(P=0, W=0, D=0, L=0, GF=0, GA=0, Pts=0) for t in teams}
    for r in s.itertuples():
        for t, gf, ga in ((r.home, r.gh, r.ga), (r.away, r.ga, r.gh)):
            v = rec[t]
            v["P"] += 1; v["GF"] += gf; v["GA"] += ga
            if gf > ga:
                v["W"] += 1; v["Pts"] += 3
            elif gf == ga:
                v["D"] += 1; v["Pts"] += 1
            else:
                v["L"] += 1
    t = pd.DataFrame(rec).T
    t["GD"] = t.GF - t.GA
    return t.sort_values(["Pts", "GD", "GF"], ascending=False)


def half_split(df: pd.DataFrame, season: str, team: str) -> dict:
    """Andata e ritorno reali per una squadra: e' il dato su cui il modello
    poggia da tre run e che finora era stimato."""
    s = df[(df.season == season) & ((df.home == team) | (df.away == team))]
    s = s.sort_values("date")
    n = len(s)
    out = {}
    for label, part in (("first_half", s.iloc[:n // 2]), ("second_half", s.iloc[n // 2:])):
        gf = ga = pts = 0
        for r in part.itertuples():
            f, a = (r.gh, r.ga) if r.home == team else (r.ga, r.gh)
            gf += f; ga += a
            pts += 3 if f > a else (1 if f == a else 0)
        out[label] = {"played": len(part), "points": pts,
                      "goals_for": gf, "goals_against": ga}
    return out


if __name__ == "__main__":
    df = load_serie_a()
    print(f"partite caricate: {len(df)}  stagioni: {df.season.nunique()}"
          f"  ({df.season.min()} -> {df.season.max()})")
    print(f"gol/partita: {df.total.mean():.4f}   "
          f"vittorie casa {(df.result == 0).mean():.3f}  "
          f"pareggi {(df.result == 1).mean():.3f}  "
          f"trasferta {(df.result == 2).mean():.3f}")
