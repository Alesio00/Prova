# Roma – Fiorentina · modello predittivo

Serie A 2026/27, Giornata 1 — Stadio Olimpico, lunedì 24 agosto 2026, 20:45 CEST.

**Roma 59.5% · Pareggio 24.7% · Fiorentina 15.8%** — xG 1.82 – 0.84 · Over 2.5 49.5% · BTTS 48.5%

Il modello **non trova valore** rispetto alle quote: concorda col mercato entro 3 punti
percentuali su tutti e tre gli esiti. Quello è il risultato, non un pronostico.

Il punto interessante sta altrove. Sulla classifica finale questa è terza contro quindicesima; sulle
ultime 19 giornate è una Roma in calo (difesa da 0.63 a 1.11 gol subiti a partita) contro una
Fiorentina che nel girone di ritorno ha fatto 29 punti, settima davanti al Milan. Modellare gli split
invece dell'aggregato sposta la Fiorentina dal 16.4% al 18.2%.

## Quick start

```bash
pip install numpy pandas scipy scikit-learn
cd src && python3 pipeline.py && python3 report.py
open ../results/report.html
```

## Com'è fatto

| Strato | File | Cosa fa |
|---|---|---|
| Dati | `data/context.json`, `data/players.json` | Ogni fatto con confidenza e fonte |
| Forza squadre | `src/ratings.py` | Rating 2025/26 → gol attesi, con shrinkage e aggiustamenti |
| Dixon-Coles | `src/dixon_coles.py` | Matrice risultati esatti con correzione bassi punteggi |
| Mercato | `src/market.py` | De-vig alla Shin, fusione log-lineare, EV e Kelly |
| Monte Carlo | `src/simulate.py` | 200k simulazioni con incertezza sui parametri, marcatori |
| ML | `src/ml.py` | Logistica + GBM + random forest, cross-validated |
| Diagnostica | `src/karpathy_checks.py` | 5 check dal *Recipe* di Karpathy: input azzerati, etichette mescolate, overfit di un batch, scala di baseline, spread fra seed |
| Duelli | `src/duels.py` | Matrice 11×11, coppie di marcatori, 45.600 storie di partita, rischio disponibilità |
| Report | `src/report.py` | HTML autonomo, light/dark |

## Documenti

- **[RESULTS.md](RESULTS.md)** — cosa funziona, cosa è fragile, cosa è stato scartato, quale bug è stato trovato
- **[HANDOFF.md](HANDOFF.md)** — come riprendere il lavoro: costanti, dipendenze, test di sanità
- **[PROMPT.md](PROMPT.md)** — prompt riusabile migliorato e quando conviene farlo girare in loop

## Livello giocatore

121 combinazioni possibili fra i due undici, **101 si incontrano davvero**. Il duello più
sbilanciato è Malen contro Pongracic (79% Malen); il più frequente è Ndicka contro Kean (70% Kean).
Per zona la Fiorentina è avanti solo sulla fascia destra della Roma, il corridoio di Gudmundsson.

Enumerando ogni combinazione di risultato e marcatori si ottengono **45.600 esiti distinti**. Il più
probabile con almeno un gol è **1-0 di Malen, al 4.1%**; la coppia più probabile è **Malen + Kean
entrambi a segno, 8.5%**. Servono 153 esiti per coprire metà della probabilità: la domanda "qual è
la combinazione più probabile" ha una risposta, e la risposta vale il 4%.

## Limite principale

L'egress di rete di questo ambiente è bloccato su tutto tranne i registri pacchetti: nessun dataset a
livello di partita era raggiungibile, l'unico canale dati è stata la ricerca web. Il layer ML è
quindi addestrato su una lega sintetica ed è **scaffolding calibrato, non una fonte di informazione**.
`HANDOFF.md § Sblocco rete` elenca cosa serve per renderlo reale.

Non è un consiglio di scommessa.
