# HANDOFF — Roma–Fiorentina, modello predittivo

Tutto quello che serve per riprendere il lavoro senza rileggere il codice.

---

## 1. In una riga

Pipeline Python che stima Roma–Fiorentina (Serie A 2026/27, G1, 24/08/2026) combinando
Dixon-Coles + Monte Carlo + mercato + un layer ML, e sputa un report HTML.
**Output attuale: Roma 59.5% · X 24.7% · Fiorentina 15.8%** — intervallo al 90% su P(Roma):
**55.6%–61.7%**. Verdetto: **nessuna scommessa**.
XI della Fiorentina basato sulla formazione reale di Coppa Italia del 14/08/2026.

## 2. Come si esegue

```bash
pip install numpy pandas scipy scikit-learn
cd src
python3 pipeline.py            # → results/predictions.json   (~3 min con ML)
python3 report.py              # → results/report.html
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
| `MARKET_WEIGHT` (`market.py`) | 0.60 | Peso del mercato nella fusione | ±2 pp per 0.1 |
| `NEW_MANAGER_DISCOUNT` | 0.55 | Quanto un allenatore al primo anno converte il rinforzo in punti | ±1.9 pp |
| `MATCHDAY1_GOAL_FACTOR` | 0.97 | Soppressione gol alla prima giornata | ±0.9 pp |
| `MATCHDAY1_EXTRA_DISPERSION` | 0.18 | Varianza extra alla prima giornata | code, non media |
| `RHO` (`dixon_coles.py`) | −0.10 | Correzione bassi punteggi | massa su 0-0 / 1-1 |
| `H2H_WEIGHT` | 0.05 | Peso dei precedenti all'Olimpico | ±0.3 pp |

**Il parametro più influente non è nessuno di questi**: è `squad_delta_2627` della Fiorentina in
`data/context.json` (escursione 8.7 pp). È un giudizio a mano. Vedi RESULTS.md.

## 5. Il vincolo che ha modellato tutto il lavoro

L'egress HTTP di questo ambiente è bloccato su tutto tranne i registri pacchetti.
Verificato: `football-data.co.uk` → 403 al CONNECT; Wikipedia, ESPN, FBref, football-italia →
`EGRESS_BLOCKED`. **L'unico canale dati è WebSearch**, che restituisce snippet, non tabelle.

Di conseguenza: niente dataset a livello di partita, quindi niente training su dati reali, quindi il
layer ML è scaffolding calibrato e non una fonte di informazione. È scritto esplicitamente sia nel
docstring di `ml.py` sia nel report.

### Sblocco rete — cosa chiedere

Aggiungere all'allowlist dell'ambiente, in ordine di utilità:

1. `football-data.co.uk` — CSV storici Serie A con risultati e quote, gratis, formato già supportato da `ml.load_real_matches()`
2. `fbref.com` / `understat.com` — xG a livello di partita e di giocatore
3. `api-football.com` o `api.football-data.org` — formazioni, infortuni, live (serve una chiave)
4. `en.wikipedia.org` — tabelle finali di campionato

Con la #1 sola: il layer ML diventa reale e RESULTS.md può iniziare a misurare la calibrazione fuori campione.

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

```bash
cd src && python3 -c "
import json,pipeline
r=pipeline.run(n_sims=200000,train_ml=False)
mc,lam=r['monte_carlo']['goals']['expected_home'],r['lambdas']['fused']['home']
assert abs(mc-lam)/lam<0.005, f'BUG sampler: {mc} vs {lam}'
p=r['probabilities']['fused_FINAL']; assert abs(sum(p.values())-1)<1e-9
print('sanity OK')"
```

## 8. Stato al passaggio di consegne

**Fatto:** raccolta dati via search · modello analitico · Monte Carlo · fusione col mercato · layer ML
con CV · analisi di sensibilità · report HTML light/dark · log RESULTS.md · un bug di sampling trovato e corretto.

**Non fatto, e perché:** nessun training su dati reali (rete bloccata) · nessuna validazione fuori
campione su partite vere (stesso motivo) · infortuni di agosto 2026 non reperibili · formazioni
ufficiali non ancora pubblicate.

**Prima cosa da fare al prossimo giro:** vedi RESULTS.md § "Prossimo run", punti 1 e 2.

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
