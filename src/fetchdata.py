"""Acquisizione dati riproducibile.

IL PROBLEMA CHE QUESTO MODULO RISOLVE
-------------------------------------
Il run 008 - quello che ha stabilito il risultato principale del progetto -
NON era riproducibile. I CSV con le quote per singolo bookmaker vivevano
nello scratchpad di una sessione che non esiste piu':

    /tmp/claude-0/.../f7c0655e-f766-5448-b6c5-7a7f2f6688ec/scratchpad

Il percorso e' hard-coded in `strategy_sharp_vs_soft.py`. La directory e'
sparita col container. Un risultato che non si puo' rieseguire e' un
aneddoto, non una misura - e questo progetto ha passato otto run a
ripetere che un numero senza verifica non vale niente.

Qui le sorgenti sono DICHIARATE: nome, URL, cosa ci si aspetta di trovare.
`python3 fetchdata.py` le riscarica in una cache stabile dentro il repo
(gitignorata: i dati restano di chi li pubblica) e stampa l'inventario.
`python3 fetchdata.py --verify` controlla senza scaricare.

IL VINCOLO DI RETE, ANCORA
--------------------------
`football-data.co.uk` - la fonte originale - resta bloccata dalla policy di
egress dell'organizzazione (403 al CONNECT, verificato nei run 006/007, non
aggirato). GitHub e' aperto. Quindi si passa dai mirror, e i mirror vanno
nominati, non trovati a caso ogni volta.
"""

from __future__ import annotations

import argparse
import glob
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / "data" / "cache"

# Le divisioni di football-data.co.uk usate qui.
DIVISIONS = {
    "E0": "Premier League (Inghilterra)",
    "I1": "Serie A (Italia)",
    "SP1": "La Liga (Spagna)",
    "D1": "Bundesliga (Germania)",
    "F1": "Ligue 1 (Francia)",
    "ARG": "Primera Division (Argentina)",
    "BRA": "Serie A (Brasile)",
}


class Source:
    """Una sorgente dati, con cosa ci si aspetta di trovarci dentro.

    `expect_files` non e' documentazione: e' un controllo. Se un mirror
    cambia struttura o sparisce, `verify()` lo dice invece di lasciare che
    l'analisi giri su meta' dei dati senza accorgersene.
    """

    def __init__(self, name: str, url: str, why: str,
                 expect_files: int, expect_glob: str):
        self.name, self.url, self.why = name, url, why
        self.expect_files, self.expect_glob = expect_files, expect_glob

    @property
    def path(self) -> Path:
        return CACHE / self.name

    def files(self) -> list[Path]:
        return sorted(Path(p) for p in glob.glob(str(self.path / self.expect_glob),
                                                 recursive=True))

    def fetch(self) -> bool:
        if self.path.exists():
            return True
        self.path.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", self.url, str(self.path)],
            capture_output=True, text=True, timeout=600)
        if r.returncode != 0:
            print(f"  ! {self.name}: clone fallito - {r.stderr.strip()[:200]}")
            return False
        return True

    def verify(self) -> tuple[bool, str]:
        if not self.path.exists():
            return False, "non scaricata"
        n = len(self.files())
        if n < self.expect_files:
            return False, f"{n} file trovati, {self.expect_files} attesi"
        return True, f"{n} file"


SOURCES = [
    Source(
        name="felipedds-football-data-co-uk",
        url="https://github.com/felipedds/football-data-co-uk",
        why=("Mirror di football-data.co.uk: 5 campionati europei x 8 stagioni "
             "(2018/19-2025/26) piu' Argentina e Brasile. Ha le colonne per "
             "singolo bookmaker - apertura E chiusura - che sono l'unico dato "
             "su cui la strategia sharp-vs-soft si puo' testare."),
        expect_files=42, expect_glob="**/*.csv"),
    Source(
        name="devaskswhy-Ball_Knowledge",
        url="https://github.com/devaskswhy/Ball_Knowledge",
        why=("Stagione 2026/27 in corso. Serve a una domanda sola: Pinnacle "
             "esiste ancora nel feed di oggi? (Risposta del run 009: no.)"),
        expect_files=4, expect_glob="data/26*/*.csv"),
    Source(
        name="openfootball-italy",
        url="https://github.com/openfootball/italy",
        why="13 stagioni di Serie A partita per partita. Usato da src/loaddata.py.",
        expect_files=10, expect_glob="*/*.txt"),
]


def fetch_all(verify_only: bool = False) -> int:
    CACHE.mkdir(parents=True, exist_ok=True)
    bad = 0
    for s in SOURCES:
        if not verify_only:
            s.fetch()
        ok, msg = s.verify()
        print(f"{'OK ' if ok else 'NO '} {s.name:<32} {msg}")
        if not ok:
            bad += 1
    return bad


def inventory() -> None:
    """Cosa c'e' davvero: per ogni file, quante partite e quali riferimenti affilati.

    PS  = Pinnacle apertura     PSC  = Pinnacle chiusura
    BFE = Betfair Exchange apertura   BFEC = Betfair Exchange chiusura
    """
    src = SOURCES[0]
    rows = []
    for f in src.files():
        head = f.open(encoding="latin-1").readline()
        cols = set(head.strip().split(","))
        n = sum(1 for _ in f.open(encoding="latin-1")) - 1
        m = re.match(r"(\d{4})_([A-Z0-9]+)\.csv", f.name) or \
            re.match(r"()([A-Z]{3})\.csv", f.name)
        season, div = (m.group(1), m.group(2)) if m else ("?", f.stem)
        rows.append((season, div, n,
                     "PSH" in cols, "PSCH" in cols,
                     "BFEH" in cols, "BFECH" in cols))

    print(f"\n{'stag':<6}{'div':<5}{'partite':>8}  {'PS':>4}{'PSC':>5}{'BFE':>5}{'BFEC':>6}")
    print("-" * 40)
    tot = 0
    for season, div, n, ps, psc, bfe, bfec in sorted(rows):
        y = lambda b: "  x " if b else "  . "
        print(f"{season or '-':<6}{div:<5}{n:>8}  {y(ps)}{y(psc)}{y(bfe)}{y(bfec)}")
        tot += n
    print("-" * 40)
    print(f"{'totale':<11}{tot:>8} partite in {len(rows)} file")
    print("\nx = colonna presente   . = assente")
    for k, v in DIVISIONS.items():
        print(f"  {k:<5} {v}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--verify", action="store_true",
                    help="controlla la cache senza scaricare niente")
    a = ap.parse_args()
    print(f"cache: {CACHE}\n")
    bad = fetch_all(verify_only=a.verify)
    if not bad:
        inventory()
    sys.exit(1 if bad else 0)
