# RESULTS — cosa funziona e cosa no

Log vivo. Ogni riga è una decisione presa e il motivo. Si aggiorna a ogni run.
Convenzione: ✅ funziona · ⚠️ funziona ma è fragile · ❌ non funziona / non usare.

---

## Run 001 — 2026-08-15 · baseline

**Output finale:** Roma **59.5%** · Pareggio **24.7%** · Fiorentina **15.8%**
xG 1.82 – 0.84 · Over 2.5 49.5% · BTTS 48.5% · risultato più probabile 1-1 (11.8%)

### ✅ Cosa funziona

| Componente | Perché ha funzionato | Evidenza |
|---|---|---|
| **Dixon-Coles con τ** | Sposta massa su 0-0 e 1-1 come serve in Serie A. Senza correzione il modello sovrastima 1-0/0-1. | ρ = −0.10, l'1-1 diventa il risultato singolo più probabile (11.8%) |
| **De-vig alla Shin** | Toglie più margine ai longshot del metodo proporzionale. Su Fiorentina a 6.40 la differenza è 0.6 pp (15.0% proporzionale → 14.3% Shin). | `market.devig_shin` vs `devig_proportional` |
| **Log-opinion pooling** | Fondere modello e mercato in spazio log è la forma corretta per due forecaster calibrati. La media aritmetica avrebbe dato più peso alla coda. | 54.5% (modello) + 62.7% (mercato) → 59.5% |
| **Retro-soluzione delle λ dalla fusione** | Risolvendo (λ,μ) che riproducono l'1X2 fuso, **tutti** i mercati derivati (O/U, BTTS, handicap, risultato esatto) restano coerenti fra loro. Senza questo passo Over 2.5 e 1X2 si contraddicono. | `market.solve_lambdas_for_probs` |
| **MC con incertezza sui parametri** | La media resta identica (1.8123 contro λ 1.815) ma le code si allargano. È l'effetto corretto — non sappiamo davvero le λ. | σ efficace 0.284 |
| **Analisi di sensibilità** | Ha identificato subito che il parametro dominante non è nessuna delle costanti del modello, ma la stima del rinforzo Fiorentina (8.7 pp di escursione). | vedi tornado nel report |

### 🔎 La scoperta che ha cambiato il modello: entrambe le squadre sono due squadre diverse

Il dato più utile del run non è un totale stagionale, è uno **split**.

**Roma.** Dopo 19 giornate: 22 GF / 12 GA, prima in classifica. A fine stagione: 54 / 33. Il girone
di ritorno è stato tutt'altra squadra — 1.68 gol fatti e 1.11 subiti a partita, contro 1.16 e 0.63
dell'andata. La stampa italiana è esplicita: "la difesa balla, i punti non arrivano".

**Fiorentina.** 13 punti nell'andata, **29 nel ritorno**: settimo posto nella classifica del solo
girone di ritorno, davanti a Milan e Bologna. Dal 7 febbraio, 18 punti in 9 partite — ritmo Champions,
fatto meglio solo da Inter e Napoli.

**Le due cose insieme ribaltano l'impostazione.** Sull'aggregato di 38 partite questa è terza contro
quindicesima. Sulle ultime 19 è terza-in-calo contro settima-in-crescita. Sono due partite diverse, e
il modello stava stimando quella sbagliata.

Aggiunto `RECENCY_WEIGHT = 0.40`: dove esistono gli split, il rating pesa il ritorno al 40%.

E una seconda costante che serviva: la forma la produce un allenatore, non solo una rosa. Gasperini è
rimasto, **Vanoli no** — la Fiorentina che ha fatto 29 punti nel ritorno adesso è allenata da Grosso.
Quindi `RECENCY_MANAGER_CHANGE_DISCOUNT = 0.50` dimezza il peso della recency per chi ha cambiato
guida tecnica. Senza questa clausola il modello avrebbe attribuito alla Fiorentina di Grosso una
forma prodotta da un altro.

| Rating | Prima (solo aggregato) | Dopo (con recency) |
|---|---|---|
| Attacco Roma | 1.17 | 1.22 |
| Difesa Roma | 0.72 | 0.84 |
| **Attacco Fiorentina** | **0.82** | **0.97** |
| **Difesa Fiorentina** | **1.15** | **1.02** |

Effetto sulla previsione del solo modello: **P(Roma) da 55.8% a 54.5%**, P(Fiorentina) da 16.4% a
18.2%, gol totali da 2.29 a 2.42.

⚠️ Corretto contestualmente un **doppio conteggio** che stavo per introdurre: `squad_delta` della
Fiorentina era +0.10/−0.10, in parte per rappresentare il loro miglioramento. Ma quel miglioramento
adesso lo porta la recency. Ripesato a +0.06/−0.05, cioè il solo effetto mercato.

### ⚠️ Cosa funziona ma è fragile

- **Numeri 2025/26 della Fiorentina.** Il 15° posto e lo split punti 13/29 sono confermati; GF 40 / GA 51 e la loro ripartizione andata/ritorno sono **derivati dai punti, non da una fonte**. Con la stessa posizione ma GF 45 / GA 47 la P(Roma) scende di ~3 pp. Primo dato da sostituire.
- **`squad_delta_2627`.** Attualmente +0.06 attacco / −0.05 difesa per la Fiorentina, quasi zero per la Roma. È un giudizio, non una misura. È **il singolo input più influente del modello** (vedi tornado): serve un vero rating dei nuovi acquisti (valori di mercato, minuti giocati, xG/90 nella lega di provenienza).
- **Quote-marcatore.** `goal_share` è un prior a mano su XI non confermate. Ordinamento plausibile (Malen 42.9%, Kean 25.3%), valori assoluti da non prendere alla lettera.
- **`home_goal_share = 0.555`.** Non confermato per la 2025/26, è il valore storico Serie A. Un errore di ±0.02 vale ~1.5 pp sulla P(Roma).

### ❌ Cosa non funziona / cose provate e scartate

| Tentativo | Esito |
|---|---|
| **Scaricare CSV storici (football-data.co.uk)** | ❌ Bloccato dal proxy di rete: `CONNECT tunnel failed, 403`. Nessun dato a livello di partita disponibile. |
| **WebFetch su Wikipedia / ESPN / FBref / football-italia** | ❌ `EGRESS_BLOCKED` su tutti. L'unico canale dati è WebSearch (snippet). |
| **Sampler Monte Carlo v1** | ❌ **Bug reale trovato e corretto.** Testavo l'accettazione Dixon-Coles solo sul blocco {0,1}×{0,1} e ri-estraevo i rifiutati da una Poisson non condizionata. Ogni rifiuto veniva sostituito da un valore mediamente più alto → media gol gonfiata a 1.91 contro λ = 1.79 (+6.5%) e P(Roma) sovrastimata di ~2.6 pp. Corretto con rejection sampling su tutta l'estrazione (`simulate._draw_scores`). **Se non avessi confrontato la media MC con la λ analitica non me ne sarei accorto: quel confronto adesso è un test permanente.** |
| **ML come fonte di informazione** | ❌ Non lo è, e va detto. Senza dati reali di partita i learner imparano il processo generativo che ho scritto io. Log loss CV 1.008 contro baseline 1.080 = imparano *qualcosa*, ma su dati sintetici. |
| **GBM meglio della regressione logistica** | ❌ Falso su questo dataset. logreg 0.9941 < rf 0.9989 < gbm 1.0045. Il DGP è liscio e monotono: il boosting overfitta rumore. Utile come promemoria: più capacità ≠ meglio nel calcio. |
| **Vantaggio casa nella lega sintetica** | ❌ **Secondo bug reale, trovato dal test di sanità.** Dopo l'aggiornamento dei rating il disaccordo ML-vs-analitico è schizzato a **+9.3 pp**, sopra la soglia di 5 pp che mi ero dato. Non era informazione nuova: era un errore. `_features()` moltiplicava per un `home_adv` centrato su 1.09 **sopra** uno split di base (1.347/1.079) che il vantaggio casa lo conteneva già — quindi lo contava due volte, e il query point usava 1.09 mentre il modello analitico no. Corretto centrando `home_adv` su 1.0 (deviazione per squadra, non valore assoluto). Verifica: la lega sintetica dà ora 41.3% vittorie casa contro il 41.6% dell'analitico media-vs-media — coerenti. |
| **H2H storico come segnale forte** | ❌ Scartato. 49-31-19 all'Olimpico sembra informativo ma ricodifica soprattutto la differenza di forza già presente nei rating. Peso tenuto a 0.05: muove ±0.3 pp. Alzarlo a 0.15 sarebbe doppio conteggio. |

### 📊 Verifica di sanità del layer ML

L'ensemble ML dà 55.4% / 24.8% / 19.8% contro il Dixon-Coles analitico 54.5% / 27.4% / 18.2%.
**Disaccordo +0.9 pp sulla Roma.** È il risultato che si voleva: i due percorsi partono dagli stessi
rating ma passano da matematiche diverse (closed-form contro appreso su un DGP sovradisperso) e
arrivano quasi allo stesso posto.

Questo controllo **non è decorativo**: nel corso del run è passato da +1.6 pp a +9.3 pp e mi ha
fatto trovare il secondo bug (doppio conteggio del vantaggio casa, vedi sotto). Dopo la correzione è
sceso a +0.9 pp. Una soglia dichiarata prima di guardare il risultato è quello che trasforma un
numero in un test.

### Confronto con il mercato

| Esito | Quota | Implicita (de-vig) | Modello | EV |
|---|---|---|---|---|
| Roma | 1.55 | 62.7% | 59.5% | −7.8% |
| Pareggio | 4.10 | 23.0% | 24.7% | +1.4% |
| Fiorentina | 6.40 | 14.3% | 15.8% | +1.2% |

**Lettura onesta:** +1.4% e +1.2% non sono un edge. Sono dentro il rumore del modello — la sola
incertezza sulla stima Fiorentina vale 8.7 pp, cioè un ordine di grandezza in più — e dentro il
margine del bookmaker. Il modello **non ha trovato valore** su questa partita.

Il risultato utile non è una scommessa. È che il modello, partendo da dati pubblici e ricostruendo
la partita da zero, arriva entro 3 pp dal mercato su tutti e tre gli esiti. Concordanza, non edge:
la conclusione corretta è che il prezzo è giusto e non c'è motivo di giocare.

Una cosa il modello la dice però più forte del mercato: **la Fiorentina è sottovalutata rispetto a
com'era a maggio.** Il mercato la prezza al 14.3%, il modello puro al 18.2%. Chi guarda solo la
classifica finale (3ª contro 15ª) vede una partita più squilibrata di quella che i dati delle
ultime 19 giornate descrivono.

---

## Prossimo run — cosa cambiare per primo

Ordinato per rapporto impatto/sforzo:

1. **Split andata/ritorno della Fiorentina** → elimina l'asimmetria della recency. Costo: una ricerca.
2. **Sbloccare un feed dati** (vedi HANDOFF § Sblocco rete). Da solo trasforma il layer ML da
   scaffolding a modello vero e rimuove metà delle stime.
3. **Tabella 2025/26 completa con GF/GA di tutte e 20 le squadre** → rating attacco/difesa stimati
   sulla lega invece che a mano, e `SERIE_A_2526` in `ml.py` smette di essere una congettura.
4. **Formazioni ufficiali (T−1h)** → `players.json` diventa reale, `squad_delta` si può ancorare ai
   minuti effettivi.
5. **Rating dei nuovi acquisti** basato su xG/90 e valori di mercato → sostituisce il giudizio a mano
   sul parametro più influente del modello.
6. **Quote di più bookmaker** → la mediana delle quote de-viggate è più stabile di una sola fonte.

---

## Template per il prossimo run

```
## Run 00N — data · cosa è cambiato
Output: Roma X% · X X% · Fiorentina X%   (delta vs run precedente: ±X pp)
Input nuovi:
✅ Cosa ha funzionato:
⚠️ Fragile:
❌ Scartato / bug trovato:
Verifica: media MC == λ analitica?   |disaccordo ML - DC| < 5 pp?
```
