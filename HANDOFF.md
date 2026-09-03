# HANDOFF — Roma–Fiorentina, modello predittivo

Tutto quello che serve per riprendere il lavoro senza rileggere il codice.

---

## 1. In una riga

Pipeline Python che stima Roma–Fiorentina (Serie A 2026/27, G1, 24/08/2026) combinando
Dixon-Coles + Monte Carlo + mercato + un layer ML, e sputa un report HTML.
**Output pubblicato: Roma 62.7% · X 23.0% · Fiorentina 14.3%** — che è il mercato de-viggato,
perché il backtest dice che il modello non aggiunge niente (peso ottimo 0.0).
Il modello da solo direbbe 55.3% / 27.1% / 17.5%.
Verdetto: **nessuna scommessa**, e il backtest spiega perché non ci sarà mai su questo mercato.

## 2. Come si esegue

```bash
pip install numpy pandas scipy scikit-learn
cd src
python3 pipeline.py            # → results/predictions.json   (~3 min con ML)
python3 report.py              # → results/report.html
```

Per la parte quantitativa sulle scommesse (run 004-009), che richiede dati storici:
```bash
python3 src/fetchdata.py       # scarica e verifica le sorgenti → data/cache/  (~2 min)
cd src && python3 validate_oos.py   # → results/validate_oos.json  (~4 min)
```

Run veloce senza ML (~5 s):
```python
import pipeline; pipeline.run(n_sims=200_000, train_ml=False)
```

## 3. Mappa dei file

| File | Cosa contiene | Quando toccarlo |
|---|---|---|
| `data/context.json` | **Tutti i dati fattuali**, ognuno con `_confidence` e `_anchor` (la citazione della fonte) | Ogni volta che arriva un dato nuovo |
| `data/players.json` | XI proiettate, quote-gol per giocatore, minuti attesi | Quando escono le formazioni |
| `src/ratings.py` | Forza squadre → gol attesi. **Tutte le costanti tunabili sono qui in cima** | Per cambiare le ipotesi del modello |
| `src/dixon_coles.py` | Matrice risultati esatti + τ, e tutte le proiezioni (1X2, O/U, BTTS, handicap) | Raramente |
| `src/market.py` | De-vig (proporzionale e Shin), log-pooling, retro-soluzione λ, tabella EV/Kelly | Per cambiare `MARKET_WEIGHT` |
| `src/simulate.py` | Monte Carlo con incertezza sui parametri + marcatori | Raramente |
| `src/ml.py` | Lega sintetica, training, CV. **`load_real_matches()` è il punto d'innesto per dati veri** | Quando arrivano dati reali |
| `src/karpathy_checks.py` | 5 check diagnostici (input azzerati, etichette mescolate, overfit di un batch, scala di baseline, spread fra seed) | **Dopo ogni modifica al layer ML** |
| `src/duels.py` | Matrice 11×11 dei duelli, coppie di marcatori, enumerazione completa delle storie di partita, rischio disponibilità | Quando cambiano le rose |
| `src/fetchdata.py` | **Acquisizione dati riproducibile.** Dichiara le sorgenti (nome, URL, contenuto atteso), le clona in `data/cache/`, verifica l'inventario | Prima di qualsiasi analisi su dati storici |
| `src/validate_oos.py` | **La validazione del run 009**: fuori tempo, fuori lega, fuori continente, sostituzione del riferimento. Bootstrap raggruppato per partita | Per rivalutare la strategia su dati nuovi |
| `src/loaddata.py` | **Parser openfootball**: 13 stagioni di Serie A, classifiche e split reali | Per aggiornare i dati storici |
| `src/backtest.py` | Backtest walk-forward, calibrazione, ECE | Prima di credere a qualsiasi modello |
| `src/backtest_odds.py` | **Il test decisivo**: train/test temporale con quote reali, simulazione scommesse con errori standard | Per rivalutare dopo ogni modifica al modello |
| `src/backtest_blend.py` | Il modello aggiunge informazione al mercato? Over/under, e dove sbaglia di più | Idem |
| `src/selfaudit.py` | **Propagazione dell'incertezza**: rifà il modello 4.000 volte campionando gli intervalli di ogni costante a giudizio. Produce l'intervallo al 90%, l'attribuzione della varianza e il verdetto finale | Prima di prendere qualsiasi decisione |
| `src/pipeline.py` | Orchestrazione + `sensitivity()` | Per aggiungere output |
| `src/report.py` | Genera l'HTML | Per cambiare la presentazione |
| `RESULTS.md` | **Log di cosa funziona e cosa no** | Dopo ogni run |

## 4. Le costanti che governano tutto

Tutte in `src/ratings.py` salvo dove indicato. L'impatto è su P(vittoria Roma).

| Costante | Valore | Cosa fa | Impatto misurato |
|---|---|---|---|
| `SHRINK` | 0.72 | Quanto i rating della scorsa stagione vengono tirati verso la media | ±4 pp |
| `RECENCY_WEIGHT` | 0.40 | Peso del girone di ritorno rispetto alla stagione intera | ±1.5 pp su 1X2, **+0.26 gol totali** |
| `RECENCY_MANAGER_CHANGE_DISCOUNT` | 0.50 | Dimezza la recency per chi ha cambiato allenatore | ~1 pp |
| `XI_DECAY_PER_DAY` | 0.0065 | ξ di Dixon-Coles. Non usato di default: implica `RECENCY_WEIGHT` 0.73 invece di 0.40 | vedi `recency_weight_from_decay()` |
| `DUEL_SLOPE` (`duels.py`) | 1.9 | Pendenza logistica dei duelli individuali | solo livello giocatore |
| `LANE_SIGMA` (`duels.py`) | 0.22 | Tolleranza laterale: quanto lontano due giocatori si incontrano ancora | solo livello giocatore |
| `MARKET_WEIGHT` (`market.py`) | **1.0** | Peso del mercato nella fusione. Era 0.60 a giudizio; **misurato** su 3.031 partite fuori campione, l'ottimo è 1.0 | il valore 0.60 peggiorava attivamente la previsione |
| `NEW_MANAGER_DISCOUNT` | 0.55 | Quanto un allenatore al primo anno converte il rinforzo in punti | ±1.9 pp |
| `MATCHDAY1_GOAL_FACTOR` | 0.97 | Soppressione gol alla prima giornata | ±0.9 pp |
| `MATCHDAY1_EXTRA_DISPERSION` | 0.18 | Varianza extra alla prima giornata | code, non media |
| `RHO` (`dixon_coles.py`) | −0.10 | Correzione bassi punteggi | massa su 0-0 / 1-1 |
| `H2H_WEIGHT` | 0.05 | Peso dei precedenti all'Olimpico | ±0.3 pp |

**Il parametro più influente non è nessuno di questi**: è `squad_delta_2627` della Fiorentina in
`data/context.json` (escursione 8.7 pp). È un giudizio a mano. Vedi RESULTS.md.

## 5. Il vincolo che credevo di avere, e che non c'era

Per tre run ho scritto che l'egress era bloccato e che l'unico canale dati era WebSearch. Vero per
`football-data.co.uk`, Wikipedia, ESPN, FBref — **falso per GitHub**, che è sempre stato
raggiungibile. L'avevo perfino usato per clonare un repo senza collegare le due cose.

I dati che servivano si prendono con un `git clone`. **Dal run 009 non farlo a mano**: le sorgenti
sono dichiarate in `src/fetchdata.py`, che le clona e ne verifica il contenuto. Il run 008 le aveva
prese a mano in uno scratchpad temporaneo, e per questo non è riproducibile.

- **openfootball/italy** — 13 stagioni di Serie A partita per partita (4.940 partite)
- **Club-Football-Match-Data** — 9.012 partite di Serie A 2000-2025 con **quote 1X2, over/under,
  handicap asiatico, tiri, corner, cartellini, Elo**

`src/loaddata.py` parsa il primo, `src/backtest_odds.py` usa il secondo.

**Lezione:** "la rete è bloccata" era una conclusione tratta da quattro tentativi falliti e mai
rimessa in discussione. Prima di dichiarare un vincolo, provare il canale che ha già funzionato.

## 6. Diramazione delle informazioni — chi dipende da cosa

```
data/context.json ──┬─> ratings.py ──> λ modello ──┐
                    │                              ├─> log-pooling ──> λ fuse ──┬─> dixon_coles ──> mercati derivati
                    └─> market.py ──> λ mercato ───┘                            │
                                                                                ├─> simulate.py ──┬─> outcome MC
data/players.json ──────────────────────────────────────────────────────────────┘                 └─> marcatori
                                                                                                          │
ml.py (lega sintetica) ──> learner ──> check di disaccordo ────────────────────────────────────────────────┤
                                                                                                          v
                                                                                            results/predictions.json
                                                                                                          │
                                                                                                          v
                                                                                              report.py ──> report.html
```

Regola: **nessun modulo inventa aggiustamenti propri.** Ogni numero che muove la previsione è una
costante nominata in `ratings.py`/`market.py` o un campo di `context.json`. Se un giorno la
previsione cambia e non si capisce perché, la causa è per costruzione in uno di quei due posti.

## 7. Test di sanità permanenti

Da rifare a ogni modifica. Se uno fallisce, c'è un bug — non una nuova intuizione.

1. **Media MC == λ analitica** (entro ~0.5%). Ha già trovato un bug reale: vedi RESULTS.md, sampler v1.
2. **|ML ensemble − Dixon-Coles| < 5 pp.** Partono dagli stessi rating: un divario grande è un errore.
3. **Somma matrice risultati == 1.0** e 1X2 dalla matrice == 1X2 dalle λ fuse.
4. **Log loss CV del ML < baseline di frequenza di classe**. Altrimenti non sta imparando niente.
5. **`python3 karpathy_checks.py` → tutti PASS.** Cinque check che devono passare dopo ogni
   modifica al layer ML. Il più importante è il primo: azzerando gli input il modello deve
   collassare esattamente sul prior. Se non lo fa, i rating non stanno entrando nel modello.
6. **Nessun "miglioramento" sotto la soglia di rumore.** `check_seed_spread` la misura: 2σ = 0.016
   di log loss. Qualsiasi guadagno più piccolo non è un guadagno.
7. **`python3 selfaudit.py` prima di ogni decisione.** Se `edge_is_an_artefact_of_market_weight`
   è `true`, l'EV trovato non è una scoperta sulla partita ma una misura del proprio scetticismo:
   la decisione corretta in quel caso è non giocare.

8. **Bootstrap raggruppato per partita, mai per selezione.** Sei quote sulla stessa partita
   condividono l'esito: non sono sei osservazioni. Misurato al run 009, raggruppare allarga gli
   intervalli di **1,3-1,6×**. Ogni intervallo calcolato sulle selezioni è troppo stretto, e il
   run 008 ne era affetto.
9. **Confronti di log loss solo sull'intersezione.** Confrontare due book sulle partite in cui
   ciascuno ha una quota non misura niente: le coperture differiscono di 4× fra book. Al run 009
   questo faceva risultare Betfair Exchange «più affilato di Pinnacle» giocando su un terzo dei
   dati. `validate_oos.h0()` fa il confronto giusto e stampa la copertura accanto.
10. **Mai apertura contro chiusura.** Confrontare la quota di apertura di un book con quella di
    chiusura del riferimento è lookahead e produce un edge inesistente. `validate_oos` lo vieta
    con un assert.

```bash
cd src && python3 -c "
import json,pipeline
r=pipeline.run(n_sims=200000,train_ml=False)
mc,lam=r['monte_carlo']['goals']['expected_home'],r['lambdas']['fused']['home']
assert abs(mc-lam)/lam<0.005, f'BUG sampler: {mc} vs {lam}'
p=r['probabilities']['fused_FINAL']; assert abs(sum(p.values())-1)<1e-9
print('sanity OK')"
```

## 8. Stato al passaggio di consegne — aggiornato al run 009

**La strategia sharp-vs-soft è morta, e si sa di cosa.** Il run 008 misurava +7,36% su Premier
League 2012-2020. Il run 009 la testa su **10.734 partite mai usate** (5 campionati europei,
2020/21-2025/26): ROI **−2,79%**, contrasto +4,37 pp, **p = 0,138**. La barra pre-registrata era
p < 0,01.

Il meccanismo è identificato, non ipotizzato: **l'overround di Pinnacle è passato da 2,02-2,05%
(run 006, campioni 2012-2020) a 3,03% (2025/26)**, e nella stagione 2026/27 le colonne Pinnacle
sono **sparite dal feed pubblico**. La strategia dipendeva interamente da quel riferimento.

Il segnale **ordina** ancora (pendenza +0,920, t a grappolo +4,09; decili monotoni, corr +0,89) ma
il livello è sotto lo zero (intercetta −0,0159). Ordinare e guadagnare sono due cose diverse.

**Due correzioni al run 008**, entrambe nella direzione di meno certezza, non di più:
1. Il suo IC 95% [+1,18%, +13,65%] trattava 55.404 selezioni correlate come indipendenti. Con il
   fattore di allargamento misurato (1,3-1,6×) diventa circa [−1,3%, +16,1%]: **lo zero torna dentro**.
2. Il suo campione era 2012-2020, cioè esattamente l'epoca in cui il riferimento era affilato.

**Fatto:** modello analitico · Monte Carlo · fusione col mercato · layer ML con CV · sensibilità ·
auto-audit · backtest con quote reali · strategia dispersione (soffitto negativo) · strategia
sharp-vs-soft (positiva 2012-2020, **nulla 2020-2026**) · acquisizione dati riproducibile.

**Non fatto, e perché:** incassabilità reale mai testata (serve un conto vero) · Argentina e Brasile
non testabili (Pinnacle e B365 non si sovrappongono: 308 partite in comune) · Betfair Exchange come
riferimento sostitutivo **promettente ma sotto-alimentato** (3.400 partite, compatibile con zero).

## LA BARRA, riscritta al run 009

La vecchia barra («log loss del modello sotto quello del mercato») è superata: cinque run hanno
stabilito che non è lì che si vince. La barra nuova riguarda l'unica strada rimasta.

**Non si testa niente su dati già usati.** Le stagioni 2020-2026 sono adesso bruciate: sono state
guardate. La prossima misura va fatta sulla **stagione 2026/27**, che si sta giocando ora.

**Pre-registrazione per il prossimo run, da fissare prima che le partite si giochino:**

> Riferimento `BFEC` (Betfair Exchange, chiusura). Bersagli `B365C`, `BWC`, `BVC`, `SKBC`.
> Accoppiamento chiusura-chiusura. Ipotesi primaria: contrasto ROI(edge>0) − ROI(edge≤0) > 0
> con **p < 0,01**, bootstrap raggruppato per partita. Nessun altro test conta.
> Se fallisce, la questione è chiusa: non c'è più un riferimento privilegiato nei dati pubblici.

**Prima cosa da fare al prossimo giro:** vedi RESULTS.md § run 009, "Cosa avrebbe senso fare adesso".

## 9. La regola che è costata un errore

**Cerca sempre l'ultima partita ufficiale giocata prima di fidarti di una formazione prevista.**
Al run 002 avevo costruito l'XI della Fiorentina sulle "formazioni tipo" dei siti di fantacalcio.
Il 14/08 la Fiorentina aveva già giocato una partita vera (4-1 al Benevento) con un modulo diverso
(4-3-2-1, non 4-3-3) e cinque titolari diversi. L'evidenza migliore era pubblica e non l'avevo
cercata.

## 10. Sul rischio Kean

`data/players.json` → `availability_risk` lo modella a `p_available = 0.80`. Non è una previsione
sul mercato: è il modo di non fingere certezza in nessuna delle due direzioni. Se prima del 24
agosto la situazione si chiarisce, quello è **un numero da cambiare, non un modello da rifare** —
metti 1.0 se resta, 0.0 se parte, e rilancia. Stesso meccanismo per Dybala (0.75, rischio di base
per età e storico infortuni, nessun problema specifico segnalato).
