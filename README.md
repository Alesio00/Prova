# Roma – Fiorentina · modello predittivo

Serie A 2026/27, Giornata 1 — Stadio Olimpico, lunedì 24 agosto 2026, 20:45 CEST.

> ## ⚠️ Due risultati negativi, entrambi misurati
>
> **1. Il modello non batte il mercato.** Su **3.031 partite fuori campione** (2017-2025, quote
> reali): log loss modello **0.9725**, mercato **0.9511**. Simulando le scommesse: **ROI −16,7%**,
> significativo. Il peso ottimo del modello nella fusione col mercato è **zero**.
>
> **2. La strategia che funzionava non funziona più.** Confrontare il prezzo di un book lento con
> quello di Pinnacle rendeva **+7,4%** su Premier League 2012-2020 (run 008). Testata su
> **10.734 partite mai usate** (5 campionati europei, 2020/21-2025/26): ROI **−2,79%**,
> **p = 0,138** contro una barra pre-registrata di p < 0,01. Il motivo è misurato:
> **l'overround di Pinnacle è passato dal 2,02% al 3,03%**, e nella stagione 2026/27 Pinnacle è
> **sparito dai dati pubblici**. La strategia dipendeva da quel riferimento.
>
> Il progetto resta utile in modo **descrittivo**. Non prezza.
> Vedi [RESULTS.md](RESULTS.md) run 004 e 009.

**Previsione pubblicata: Roma 62.7% · Pareggio 23.0% · Fiorentina 14.3%** — che è il mercato
de-viggato, perché è quello che il backtest dice di pubblicare.

Il modello da solo direbbe 55.3% / 27.1% / 17.5%. La differenza è la misura di quanto si
sbaglierebbe a dargli retta.

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

La parte quantitativa sulle scommesse (run 004-009) richiede i dati storici:

```bash
python3 src/fetchdata.py            # sorgenti dichiarate → data/cache/
cd src && python3 validate_oos.py   # → results/validate_oos.json
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
| Dati storici | `src/fetchdata.py` | Sorgenti dichiarate e verificate: 26.054 partite con quote per singolo bookmaker |
| Validazione | `src/validate_oos.py` | Fuori tempo, fuori lega, fuori continente; bootstrap raggruppato per partita |
| Diagnostica | `src/karpathy_checks.py` | 5 check dal *Recipe* di Karpathy: input azzerati, etichette mescolate, overfit di un batch, scala di baseline, spread fra seed |
| Duelli | `src/duels.py` | Matrice 11×11, coppie di marcatori, 46.209 storie di partita, rischio disponibilità |
| Auto-audit | `src/selfaudit.py` | Rifà il modello 4.000 volte campionando gli intervalli di ogni costante: intervallo al 90%, attribuzione della varianza, verdetto |
| Report | `src/report.py` | HTML autonomo, light/dark |

## Documenti

- **[RESULTS.md](RESULTS.md)** — cosa funziona, cosa è fragile, cosa è stato scartato, quale bug è stato trovato
- **[HANDOFF.md](HANDOFF.md)** — come riprendere il lavoro: costanti, dipendenze, test di sanità
- **[PROMPT.md](PROMPT.md)** — prompt riusabile migliorato e quando conviene farlo girare in loop

## Livello giocatore

121 combinazioni possibili fra i due undici, **101 si incontrano davvero**. Il duello più
sbilanciato è Malen contro Ranieri (80% Malen); il più frequente è Ndicka contro Kean (73% Kean).
Per zona la Fiorentina è avanti solo sulla fascia destra della Roma, il corridoio di Gudmundsson.

Enumerando ogni combinazione di risultato e marcatori si ottengono **46.209 esiti distinti**. Il più
probabile con almeno un gol è **1-0 di Malen, al 4.1%**; la coppia più probabile è **Malen + Kean
entrambi a segno, 9.1%**. Servono 155 esiti per coprire metà della probabilità: la domanda "qual è
la combinazione più probabile" ha una risposta, e la risposta vale il 4%.

## Il modello che verifica se stesso

Il 35.6% della varianza di P(vittoria Roma) viene da `MARKET_WEIGHT` — cioè da **quanto peso decido
di dare al mercato**, non da un fatto sul calcio. Condizionando l'EV su quel parametro, l'"edge" sul
pareggio va da +4.6% a −1.1% e cambia segno: non era una scoperta sulla partita, era la misura del
mio scetticismo verso il banco. Il modello adesso se ne accorge da solo.

Nessuna selezione resta in profitto in più del 64% dello spazio dei parametri plausibili. Verdetto:
**non si gioca**.

## La cosa che il progetto ha davvero stabilito

Non si batte il mercato prevedendo meglio il calcio: provato e misurato in cinque modi diversi.

Si batteva — al passato — confrontando il prezzo di un book lento con quello di un book affilato. Il
run 007 ha isolato il meccanismo con un esperimento di controllo: conta **l'affilatezza del
riferimento**, non il modello né la quantità di dati. Con un riferimento non affilato e 900.988
selezioni, il segnale è esattamente **zero**.

Il run 009 mostra la stessa cosa lasciando scorrere il tempo invece di cambiare il riferimento:
il riferimento si è smussato da solo, e il segnale è uscito con lui.

> **Una strategia che dipende da un riferimento privilegiato ha la vita di quel riferimento.**

## Limiti

- Il layer ML è addestrato su una lega sintetica: è **scaffolding calibrato, non una fonte di
  informazione**. `football-data.co.uk` resta bloccato dalla policy di egress; i dati arrivano dai
  mirror GitHub dichiarati in `src/fetchdata.py`.
- Il run 008 non è riproducibile: i suoi dati vivevano in uno scratchpad temporaneo. Dal run 009
  l'acquisizione è dichiarata e verificata.
- Gli intervalli di confidenza calcolati sulle *selezioni* invece che sulle *partite* sono troppo
  stretti di un fattore **1,3-1,6×**. Vale per il run 008 e va ricontrollato sugli altri.

Non è un consiglio di scommessa.
