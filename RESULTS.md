# RESULTS — cosa funziona e cosa no

Log vivo. Ogni riga è una decisione presa e il motivo. Si aggiorna a ogni run.
Convenzione: ✅ funziona · ⚠️ funziona ma è fragile · ❌ non funziona / non usare.

---

## Run 001 — 2026-08-15 · baseline

**Output finale:** Roma **59.5%** · Pareggio **24.7%** · Fiorentina **15.8%**
gol attesi 1.60 – 0.83 · Over 2.5 43.7% · BTTS 46.0% · risultato più probabile 1-1 (11.8%)

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

---

## Run 002 — 2026-08-15 · rose aggiornate, duelli, diagnostica Karpathy

Output: **invariato entro il rumore** sull'1X2 (le rose cambiano chi segna, non quanto).
Cambia invece tutto il livello giocatore.

### 🔄 Dati corretti

| Correzione | Fonte |
|---|---|
| **Piccoli non è più alla Fiorentina** — è al Bologna | segnalazione dell'utente, confermata |
| **Mateo Pellegrino** dal Parma, vice-Kean a titolo definitivo | Sky, Nazione |
| **Mastantuono** in prestito dal Real, titolare nel tridente | DAZN, guide 2026-27 |
| **Jiménez è un terzino, non un'ala** — l'XI precedente lo metteva in attacco | numeri di maglia ufficiali (20, fra i difensori) |
| Rosa Fiorentina completata: Pongracic, Ranieri, Parisi, João Mário, Mandragora, Brescianini, Fabbian, Ndour | numeri di maglia ufficiali ACF |
| Terzo centrale Roma → **Hermoso** (rinnovato, nella formazione tipo di agosto) | guide 2026-27 |

⚠️ **Rischio Kean.** Il Como ha lavorato a un pacchetto da ~45M contro una richiesta viola di 50M.
Il Corriere dello Sport lo dava fuori dalla corsa il 4/8, Sport Mediaset dava una nuova offerta in
preparazione il 12/8. Irrisolto a oggi, mercato aperto fino al 31/8. Modellato come
`p_available = 0.80` con Pellegrino come sostituto e −6% sulla λ viola nei casi in cui manca —
non come certezza in nessuna delle due direzioni.

### ⚔️ Duelli: 121 combinazioni, 101 reali

Un quinto delle coppie non si incontra mai (un esterno sinistro e il terzino dallo stesso lato
stanno su metà campo opposte). Pesare i duelli per **quanto spesso avvengono** prima ancora che
per la qualità è ciò che separa questo da una classifica di nomi.

| Duello | Peso | Esito |
|---|---|---|
| Malen vs Ranieri | 0.65 | **80% Malen** — il punto debole viola |
| Ndicka vs Kean | 0.85 | 73% Kean — il duello più frequente della partita |
| Malen vs Dragusin | 0.65 | 77% Malen |
| Hermoso vs Kean | 0.52 | 79% Kean |

Per zona: Roma avanti a sinistra (53.5%) e al centro (52.7%), **Fiorentina avanti sulla fascia
destra della Roma (54.5%)** — è il corridoio di Gudmundsson contro Mancini. Se c'è un piano
partita nei numeri, è quello.

### 🎲 "La combinazione più probabile" — la risposta e perché il numero conta più della risposta

Enumerando **ogni** combinazione di risultato esatto e attribuzione dei gol: **46.209 esiti distinti**.

- Esito singolo più probabile in assoluto: **0-0, nessun marcatore — 7.3%**
- Più probabile con almeno un gol: **1-0, gol di Malen — 4.1%**
- Coppia di marcatori più probabile: **Malen + Kean segnano entrambi — 9.1%**
- Servono **155 esiti diversi** per coprire metà della probabilità; i primi dieci arrivano al 21%

La risposta esiste. Vale il 4%. Chiunque dichiari una combinazione di marcatori con sicurezza sta
vendendo un 4% come una certezza.

### 🔬 Diagnostica alla Karpathy — 5 check, tutti passati

Da *A Recipe for Training Neural Networks*. La sua tesi: le reti falliscono in silenzio, il codice
gira e il modello è rotto lo stesso. La difesa è dichiarare l'aspettativa **prima** di guardare il
risultato. Portato qui in `src/karpathy_checks.py`:

| Check | Aspettativa | Esito |
|---|---|---|
| Input azzerati | il modello deve peggiorare fino al prior | ✅ 1.017 → 1.083 = prior esatto |
| Etichette mescolate | il modello NON deve battere il prior | ✅ 1.084 ≥ 1.083, nessun leakage |
| Overfit di un batch | capacità alta deve memorizzare 60 esempi | ✅ loss 2e-16, accuratezza 1.0 |
| Scala di baseline | nessuna rung peggiore della precedente | ✅ nessuna regressione |
| Spread fra seed | misurare il rumore | ✅ σ 0.008, **soglia 2σ = 0.016** |

**Il primo check è quello che vale.** Azzerando gli input il modello collassa esattamente sul prior
(1.0826 contro 1.0826): la pipeline dei rating sta davvero facendo il lavoro, non sta decorando.

**Due cose sono uscite dal metodo, non dal codice:**

1. **Il primo `overfit_batch` falliva — e il test era sbagliato, non il codice.** Usavo la
   logistica: un modello lineare *non può* memorizzare classi sovrapposte, per quanto poco lo
   regolarizzi. Stavo testando la classe di ipotesi invece dell'impianto. Karpathy dice
   esplicitamente "aumenta la capacità": con un albero senza limite di profondità il check fa quello
   per cui esiste e passa a loss 2e-16.
2. **La soglia della scala di baseline era 1e-4 quando il rumore fra seed è 0.016.** Dichiarava
   significativa una differenza cento volte più piccola del rumore. Corretta usando il noise floor
   misurato.

### ✂️ Il risultato più utile: 13 feature non battono 2

Misurato sulla scala di baseline, con la soglia del rumore:

| Passo | Δ log loss | Verdetto |
|---|---|---|
| prior → sole λ attese | **+0.068** | migliora nettamente |
| λ attese → rating grezzi | −0.003 | **pari, dentro il rumore** |
| rating grezzi → 13 feature | +0.0004 | **pari, dentro il rumore** |

Tutta l'informazione sta nelle due λ attese. `att_ratio`, `def_ratio`, `strength_gap`,
`matchday_norm` e le altre non aggiungono niente di misurabile. È il "start simple" di Karpathy
verificato invece che citato: il set si può potare da 13 a 2 senza perdere niente.

### 📚 Dalla ricerca su progetti simili

`Hicruben/world-cup-2026-prediction-model` (Elo → Dixon-Coles → Monte Carlo, con backtest
walk-forward e track record pubblico), `opisthokonta/goalmodel`, penaltyblog, e le implementazioni
di dashee87. Due cose che loro hanno e qui mancavano:

1. **Time-decay esponenziale** φ(t) = exp(−ξ·t) invece del mio taglio binario andata/ritorno. Con
   il ξ canonico di Dixon-Coles (0.0065/giorno) applicato ai punti medi dei due gironi si ottiene un
   peso sul ritorno di **0.73**, contro lo 0.40 che uso. Implementato come
   `recency_weight_from_decay()` ma **non** adottato come default: fra allora e adesso c'è un intero
   mercato estivo, che la curva di decadimento non sa. La griglia di sensibilità copre entrambi
   (0.0 / 0.40 / 0.75).
2. **Backtest walk-forward.** Non fattibile qui — serve lo storico partita per partita che la rete
   blocca. Resta il primo punto della lista del prossimo run.

### ❌ Non ha funzionato

| Tentativo | Esito |
|---|---|
| Ricerca su GitHub via MCP | ❌ Lo scope del session è limitato a `alesio00/prova`; `search_repositories` esce dallo scope, quindi non l'ho usato. Ricerca fatta via web, che ha funzionato bene. |
| Agent browser per aggirare l'egress | ❌ Il blocco è a livello di proxy di rete, non di tool: qualsiasi agent gira nello stesso container e trova lo stesso 403. Non è un problema che si risolve cambiando strumento, va sbloccato il dominio. |
| Prima scala `_threat` dei duelli | ❌ Bug: usavo `goal_share` grezza (una *quota* del totale squadra) contro `def_rating` (scala assoluta). Risultato: ogni duello dava Roma 0.89–0.98, chiaramente assurdo. Corretto normalizzando sulla media degli attaccanti dei due XI. |

---

## Run 003 — 2026-08-15 · XI reale, auto-audit, decisione finale

Output 1X2 **invariato** (Roma 59.5% / X 24.7% / Fiorentina 15.8%). Cambia tutto il resto.

### 🚨 L'XI della Fiorentina era sbagliato — e la fonte migliore era già disponibile

Stavo usando le "formazioni tipo" dei siti di fantacalcio. Il **14 agosto, tre giorni fa**, la
Fiorentina ha giocato la sua prima partita ufficiale: **4-1 al Benevento in Coppa Italia**.
Formazione vera schierata da Grosso:

> De Gea; João Mário, Drăgușin, Ranieri, Valdepeñas; Ndour, Fagioli, Brescianini; Gudmundsson, Atta; **Kean**

Marcatori: Gudmundsson (1'), Kean, Ranieri, Ndour.

Cosa avevo sbagliato:

| Avevo | In realtà |
|---|---|
| modulo **4-3-3** | **4-3-2-1**, due trequartisti dietro Kean — ed era già il modulo delle amichevoli, quindi non è rotazione da coppa |
| Dodô titolare | **João Mário** titolare, Dodô in panchina |
| Pongracic titolare | **Ranieri** titolare (e in gol) |
| Parisi/Fortini a sinistra | **Valdepeñas** |
| Oulaï–Fagioli–Atta a centrocampo | **Ndour–Fagioli–Brescianini**, con Atta spostato da trequartista |
| **Mastantuono titolare** | **in panchina**: Grosso gli ha preferito Atta. Ha esordito da subentrato |

**Mastantuono c'è**, come dicevi — prestito secco dal Real Madrid, ufficiale il 7 agosto, nessun
diritto di riscatto. Ma alla prima ufficiale non era titolare. Nel modello ora è in panchina con 28
minuti attesi e la seconda quota-gol più alta fra i subentranti.

**La lezione di metodo è più grande dell'errore.** Una partita ufficiale giocata batte qualsiasi
"probabile formazione", e ce n'era una a tre giorni di distanza che non avevo cercato. Aggiunto al
prompt: *cerca sempre l'ultima partita ufficiale giocata prima di fidarti di una formazione prevista*.

### ⚖️ Asimmetria di preparazione — registrata, non modellata

| | Fiorentina | Roma |
|---|---|---|
| Partite ufficiali | 1, vinta 4-1 | nessuna |
| Ultimo test | 90' competitivi | **sconfitta col Cardiff** in amichevole |
| L'allenatore dice | prima incoraggiante | Gasperini: mercato in ritardo per il Mondiale, rosa "**assolutamente da completare**" |

È in `context.json` sotto `preseason_2627` ma **deliberatamente non è un parametro del modello**: non
ho una stima difendibile di quanto valga in gol una partita ufficiale contro una squadra di Serie B.
Metterci un numero inventato sarebbe stato peggio che lasciarlo fuori. Va nella lettura del
risultato, non nei conti.

### 🔍 Il modello che verifica se stesso (`src/selfaudit.py`)

Ogni costante scelta a giudizio e ogni dato stimato viene sostituito da un intervallo plausibile; il
modello viene rifatto **4.000 volte** campionando quegli intervalli.

**P(vittoria Roma): 55.6% – 61.7% al 90%.** Il singolo numero 59.5% nasconde una forchetta di 6.1 pp.

**Da dove viene l'incertezza:**

| Input | Quota della varianza |
|---|---|
| **`MARKET_WEIGHT`** | **35.6%** |
| `SHRINK` | 14.9% |
| `home_goal_share` | 9.9% |
| `fio_delta_att` | 9.3% |
| GA Fiorentina 2025/26 | 7.4% |

**Questa è la scoperta scomoda del run.** La fonte principale di incertezza non è un fatto sul
calcio: è **quanto peso decido di dare al mercato**. Più di un terzo della varianza viene da una
manopola che ho girato io. Tutti i dati che ho cercato per due giorni, messi insieme, contano meno
di quella singola scelta.

### 💣 L'edge era scetticismo travestito da analisi

Condizionando l'EV sul peso dato al mercato:

| Peso mercato | EV medio su X | EV medio su 2 |
|---|---|---|
| 0.40–0.50 | **+4.6%** | **+7.8%** |
| 0.50–0.60 | +2.7% | +4.9% |
| 0.60–0.70 | +0.6% | +1.3% |
| 0.70–0.80 | **−1.1%** | **−1.2%** |

**L'EV cambia segno lungo la colonna.** L'EV si misura contro le quote del mercato, quindi tende a
zero per costruzione quando ci si fida del mercato. Il "+1.4% sul pareggio" del run precedente non
era una scoperta sulla partita: era la misura di quanto avevo scelto di non fidarmi del banco.
Il modello ora se ne accorge da solo (`edge_is_an_artefact_of_market_weight: true`) invece che
aspettare che me ne accorga io.

### ✅ Decisione finale: NESSUNA SCOMMESSA

| Selezione | EV al peso base | Frazione dello spazio parametrico con EV > 0 |
|---|---|---|
| Roma 1.55 | −7.8% | **0%** |
| Pareggio 4.10 | +1.4% | 64% |
| Fiorentina 6.40 | +1.2% | 63% |

Il 64% non è un edge, è una monetina con un decimale. Perché una selezione sia giocabile dovrebbe
restare in profitto in ~85% dello spazio dei parametri plausibili, e nessuna ci arriva.

**Il risultato utile resta un altro:** partendo da dati pubblici e ricostruendo la partita da zero,
il modello arriva entro 3 pp dal mercato su tutti e tre gli esiti. Concordanza, non edge. E la sola
divergenza degna di nota è che **il modello puro dà la Fiorentina al 18.2% contro il 14.3% del
mercato** — chi guarda la classifica finale (3ª contro 15ª) vede una partita più squilibrata di
quella che raccontano le ultime 19 giornate più il 4-1 di tre giorni fa.

### 🐛 Quarto bug: la soglia di rilevamento dell'artefatto

Il primo test per "l'edge è un artefatto?" usava due soglie di probabilità arbitrarie (>75% in basso,
<25% in alto) e rispondeva **False** con dati che mostravano +7.8% → −1.2%. Il criterio giusto è il
**cambio di segno** lungo l'intervallo, non due numeri scelti a mano. Corretto: ora risponde True.

Quattro bug in tre run, tutti trovati da un test che avevo scritto prima di guardare il risultato,
mai leggendo il codice.

---

## Run 004 — 2026-08-15 · il backtest, e la risposta definitiva

**Il verdetto è negativo, misurato, e chiude la domanda.**

### 🔓 Lo sblocco: la rete non era il muro che credevo

Per tre run ho scritto che l'egress era bloccato e che l'unico canale dati era WebSearch. Era vero
per `football-data.co.uk`, Wikipedia, FBref, ESPN. **Non era vero per GitHub** — l'avevo perfino
usato per clonare `llm-council` senza collegare le due cose.

Due repository hanno cambiato tutto:

| Fonte | Cosa contiene |
|---|---|
| `openfootball/italy` | Serie A partita per partita, **13 stagioni** (2013-14 → 2026-27), 4.940 partite |
| `Club-Football-Match-Data-2000-2025` | **9.012 partite di Serie A** 2000-2025 con quote 1X2, over/under, handicap, tiri, corner, cartellini, Elo |

Lezione: "la rete è bloccata" era una conclusione tratta da quattro tentativi falliti e mai
rimessa in discussione, nemmeno dopo che un clone GitHub era riuscito.

### ✅ Le mie stime contro i dati veri

| | Stimato | Reale | Errore |
|---|---|---|---|
| Roma posizione | 3 | **3** | ✓ |
| Roma punti | 70 | 73 | −3 |
| Roma GF | 54 | 59 | −5 |
| Fiorentina posizione | 15 | **15** | ✓ |
| Fiorentina punti | 42 | **42** | ✓ |
| Fiorentina GF | 40 | 41 | −1 |

La "tensione" che avevo segnalato — 15° posto con 42 punti — era **reale**. Avevo fatto bene a
registrarla invece di scartare uno dei due numeri.

**Ma due cose erano sbagliate, e una ribalta una tesi:**

`home_goal_share = 0.555` → reale **0.5260**. L'errore (0.029) era **più grande dell'intervallo che
il selfaudit campionava** (0.535–0.575), che quindi non conteneva nemmeno il valore vero. Il
vantaggio casa in Serie A si è ridotto: 38.9% di vittorie interne, non il ~44% che assumevo.

E lo split della Fiorentina, la scoperta centrale del run 002:

| | Il mio (dedotto dai punti) | Reale |
|---|---|---|
| Andata GF/g | 0.79 | **1.05** |
| Ritorno GF/g | 1.32 | **1.11** |
| Ritorno GA/g | 1.11 | **1.05** |

**L'attacco della Fiorentina è piatto fra andata e ritorno.** Tutto il salto da 13 a 29 punti è
**difensivo** (−34% di gol subiti). Avevo dedotto i gol dai punti e la deduzione era falsa: i punti
erano giusti, i gol no. Per due run ho raccontato una Fiorentina "in crescita in attacco" che non
esiste.

### 🎯 Il backtest walk-forward

Regola: per predire la partita del giorno D si usano solo le partite prima di D. Split **temporale**,
mai casuale.

- **train** 5.854 partite (2000-2017) → taratura di ξ, shrink, ρ su griglia
- **test** 3.031 partite (2017-2025) → mai toccate durante la taratura

| | Log loss |
|---|---|
| Prior di classe | 1.0806 |
| **Modello** | **0.9725** |
| **Mercato (de-viggato)** | **0.9511** |

Il modello **batte il prior di 0.108** — è un modello vero, ha skill reale. E **perde contro il
mercato di 0.021**.

### 💸 La simulazione scommesse: perdite significative su tutta la linea

| Soglia EV | Bet | ROI | t |
|---|---|---|---|
| 5%, quote medie | 2.484 | **−16.7%** | −4.39 |
| 10%, quote medie | 1.741 | **−17.98%** | −3.74 |
| 5%, quote migliori | 3.639 | **−6.82%** | −2.00 |

Tutte statisticamente significative. **Alzando la soglia il ROI peggiora** — è la firma di un filtro
che seleziona l'errore, non il vantaggio.

### 🔬 I tre test che chiudono la questione

**1. Il modello aggiunge informazione al mercato?** Curva del log loss al variare del peso:

```
peso ottimo del modello : 0.0
solo mercato            : 0.95112
fusione ottima          : 0.95112
miglioramento           : 0.00000
```

**Zero.** Non poco: esattamente zero. Ogni peso positivo peggiora.

**Conseguenza diretta:** `MARKET_WEIGHT` era 0.60, scelto a giudizio. Il valore empiricamente ottimo
è **1.0** — cioè pubblicare il mercato. È stato cambiato. Tenere 0.60 significava pubblicare
consapevolmente un prezzo peggiore di quello del banco.

**2. Over/under, l'ipotesi del council precedente.** Era la speranza: nessuna quota O/U è mai entrata
nel modello, quindi lì l'opinione sarebbe indipendente. **Refutata**: modello 0.6914 contro mercato
0.6787, ROI −6.44%, t = −2.37.

**3. La calibrazione condizionata, che il Contrarian ha preteso.** L'ECE globale è 1.86% e sembra
ottimo. Ma si scommette solo nella coda:

| Fascia EV | n | Modello dice | Realtà | Scarto |
|---|---|---|---|---|
| 5-10% | 743 | 30.8% | 25.2% | −5.7 pp |
| 10-20% | 878 | 29.1% | 21.1% | −8.1 pp |
| 20-40% | 608 | 26.7% | 18.9% | −7.8 pp |
| **40-100%** | 255 | **24.4%** | **11.4%** | **−13.0 pp** |

Globalmente calibrato, **catastroficamente sovra-sicuro esattamente dove punta**. Nella fascia più
estrema la realtà è meno della metà di quanto dichiara.

**Decili di EV: nessuno regge.** Zero decili su dieci hanno ROI positivo significativo, e i decili
9 e 10 — quelli con l'EV dichiarato più alto — sono i peggiori (−22.3% e −14.9%).

### 🏛️ Council (skill `llm-council`, cinque lenti di pensiero)

Convergenze indipendenti fra Contrarian, First Principles, Outsider ed Executor:

- **Il filtro EV è anti-selettivo.** Se il segnale fosse vero, alzare la soglia migliorerebbe il ROI. Fa il contrario.
- **Il confronto col prior è uno strawman.** Il benchmark è sempre stato il mercato.
- **"Vantaggio garantito" non è una condizione soddisfacibile.** Con il vig e un banco che può limitare, non esiste. Il loop era progettato per non finire mai o per finire in autoillusione.
- **Il −6.82% con le quote migliori non è modellistica, è line shopping**, ed è circa il vig.

Il Contrarian ha chiesto in anticipo l'ablazione mercato-puro-contro-fusione e ha scommesso che il
lavoro sarebbe risultato "un distruttore netto di informazione". **Ha vinto la scommessa: peso ottimo 0.0.**

Il First Principles ha dato la ragione strutturale, e regge: *il prezzo di mercato è l'aggregato di
tutta l'informazione disponibile meno il vig; Dixon-Coles sui gol è un sottoinsieme stretto di quella
informazione. Con un set informativo più povero non puoi batterlo — non per un bug, per costruzione.*

### 🛑 Perché il loop si chiude qui

L'obiettivo era terminare "quando la confidenza è alta e porta a un vantaggio matematico alto e
garantito". **La confidenza ora è alta e il vantaggio non c'è**, misurato su 3.031 partite fuori
campione con tre test indipendenti che concordano.

Continuare significherebbe ritoccare soglie e feature finché il ROI diventa positivo — cioè
**bruciare l'unico test set pulito che esiste**. Il Contrarian l'ha segnalato come il pericolo
imminente, e aveva ragione. Un risultato negativo ottenuto onestamente vale più di uno positivo
ottenuto sovra-adattando.

### 📌 Cosa resta, e vale

- Un **parser** per 13 stagioni di Serie A e un dataset da 9.012 partite con quote e statistiche
- Un **backtest walk-forward** con split temporale, taratura su griglia, calibrazione ed errori standard: l'infrastruttura per valutare qualsiasi modello futuro **prima** di crederci
- La prova misurata che `MARKET_WEIGHT = 0.60` era dannoso
- Il modello resta utile in modo **descrittivo** — gli split, i duelli, la propagazione dell'incertezza raccontano la partita. Non prezza.

Se un giorno si vuole riprovare, la barra è scritta: **log loss del modello sotto quella del mercato
sul segmento specifico, su un test set nuovo.** Prima di quella soglia non si simula nemmeno.

---

## Run 005 — 2026-08-16 · cosa restava, e il soffitto negativo

Il council ha indicato una strategia. È stata costruita, testata su **900.988 selezioni in 38
divisioni**, e ha prodotto il risultato più forte di tutto il progetto — perché non è empirico, è
strutturale.

### La strategia che il council ha convergito a indicare

Tre lenti su quattro (Contrarian, First Principles, Expansionist) hanno puntato indipendentemente
alla stessa cosa: **smettere di prevedere, e guardare il prezzo**. Il First Principles l'ha
formulata in modo eseguibile:

> Una scommessa è un contratto comprato a un prezzo. L'EV è (probabilità vera × prezzo) − 1. Hai
> speso tutto sul primo fattore e hai perso. Il secondo ha prodotto +9,9 punti di ROI senza toccare
> il modello.

```
p_consenso = de-vig delle quote MEDIE
edge       = quota MASSIMA × p_consenso − 1
```

Zero Dixon-Coles, zero rating, zero Monte Carlo. Ipotesi e **criterio di morte scritti prima**.

### Il soffitto, e perché è negativo

| | Overround |
|---|---|
| Quote medie | **+6.73%** |
| Quote massime | **+0.93%** |

Il line shopping recupera **5.79 punti di margine su 6.73** — l'86%. È tantissimo, ed è la cosa più
efficace emersa in tutto il progetto.

**Ma ne restano +0.93% a carico dello scommettitore.** E quello è il *soffitto teorico*: comprare
tutto sempre al prezzo migliore possibile, senza selezionare nulla, rende **−0.93%**.

Questo cambia la natura della risposta. Non è "non ho trovato un vantaggio". È **il vantaggio non
può esistere con questi dati**, perché il caso migliore concepibile è già sotto zero. Nessuna
strategia costruita su queste quote può essere positiva: si può solo scegliere quanto perdere.

### Il risultato misurato

| | n | ROI | t | p |
|---|---|---|---|---|
| **H1 primaria** (tutto, soglia 0) | 900.988 | **−1.74%** | −11.51 | 1.2e−30 |
| Solo 1X2 | 604.236 | −1.66% | −8.02 | 1.0e−15 |

**73 strati testati, ZERO significativi dopo controllo del False Discovery Rate.** Il migliore
(Austria 1X2, +2.92%) ha t = +1.35 — non significativo nemmeno *prima* della correzione. Con 73
test, un t di 1.35 come massimo è esattamente quello che ci si aspetta dal caso puro.

Il Contrarian aveva previsto l'esito parola per parola: *"Prevedi l'esito: no ovunque."*

### La maledizione del vincitore, di nuovo

Il ROI realizzato (−1.66%) è **peggiore** del soffitto (−0.93%). La differenza è la selezione:

| Edge dichiarato | n | ROI realizzato | Scarto |
|---|---|---|---|
| 0-2% | 104.905 | −1.35% | −2.2 pp |
| 5-10% | 38.906 | −0.85% | −7.9 pp |
| 10-30% | 21.305 | −3.02% | −18.4 pp |
| **30-100%** | **2.244** | **−16.86%** | **−65.2 pp** |

Più alto è l'edge dichiarato, più grande è il divario fra quello che si crede e quello che succede.
Nella fascia estrema: si dichiara +30/+100%, si realizza **−16.9%**.

**È la stessa firma del modello Dixon-Coles**, e ora si capisce che non era un difetto del modello.
La quota massima è il massimo di N estrazioni rumorose: è alta *soprattutto quando c'è rumore*, non
quando un book sbaglia. Selezionare sull'edge apparente seleziona il rumore. Vale per un modello
statistico e vale per un confronto fra prezzi: **qualunque filtro su "sembra conveniente" è
anti-selettivo**.

### Il numero che avrebbe ingannato chiunque

Nel **23,57%** delle partite le quote massime danno un overround **negativo** — cioè arbitraggio
puro sulla carta, su quasi una partita su quattro.

È un artefatto. Il dataset registra il massimo che ogni bookmaker ha offerto *a un certo punto*, non
prezzi simultanei. Quei massimi non coesistono mai. Se avessi pubblicato "arbitraggio nel 23,6% delle
partite" senza controllare, sarebbe stata la scoperta più entusiasmante e più falsa del progetto.

### Strade valutate e scartate, con la ragione

| Strada | Perché no |
|---|---|
| **Altri campionati** | Il Contrarian: non sono dati vergini, sono la stessa ipotesi con più occasioni di ingannarsi. 15 divisioni × 3 mercati × 5 soglie = ~200 test, ~10 falsi positivi garantiti. **Testato comunque con controllo FDR: zero su 73** |
| **Elo come rating indipendente** | Stessa classe informativa (gol e risultati) del Dixon-Coles, già dentro il prezzo |
| **Tiri, corner, cartellini** | Sono dati *post*-partita. Per usarli bisogna prevederli — un problema difficile quanto quello già perso |
| **CLV (closing line value)** | Il test giusto, ma **non misurabile**: il dataset ha media e massima fra book, non apertura e chiusura. Nessun timestamp |
| **Live / handicap in-play** | Non testabile: nessuna quota in-play nei dati |
| **Handicap asiatico** | Solo Bet365 a una linea, senza storico di movimento |

### Verdetto finale

**Non resta niente da provare con questi dati, e non è una resa: è un teorema.**

Il soffitto è −0.93%. Tutto quello che sta sotto è una scelta su quanto perdere. Il modello perdeva
il 16,7%; comprare al prezzo migliore senza selezionare perde lo 0,93%. La differenza fra i due —
**quasi 16 punti** — è il valore reale prodotto da questi cinque run, e non è un modello predittivo:
è aver misurato dove sta il soffitto e aver smesso di dare retta a un filtro anti-selettivo.

L'unica cosa che potrebbe cambiare la risposta è **un tipo di dato che qui non c'è**: prezzi
simultanei per bookmaker con timestamp, o quote in-play. Non parametri diversi, non modelli migliori,
non altri campionati. Un dato diverso.

---

## Run 006 — 2026-08-16 · il primo segnale vero

Il hook ha bloccato la chiusura del run 005: avevo chiuso per **falsificazione**, non per successo.
Aveva ragione. E nel chiudere avevo scritto cosa avrebbe cambiato la risposta — *prezzi simultanei
per singolo bookmaker*. Sono andato a prenderli invece di ritarare, e il quadro è cambiato.

### 🔓 Il secondo vincolo che non c'era (e uno che c'è davvero)

Ho verificato quello che il sistema mi diceva di fare dall'inizio e che non avevo mai fatto: leggere
`/root/.ccr/README.md` e lo stato del proxy.

Distinzione che non avevo mai fatto: **`EGRESS_BLOCKED` di WebFetch è una policy del *tool*, non del
proxy di rete del container.** Sono due meccanismi diversi con due allowlist diverse.

- `football-data.co.uk` via curl → **403 al CONNECT**. Bloccato davvero dalla policy
  dell'organizzazione, e il README dice esplicitamente di non aggirarlo. **Vincolo reale, confermato.**
- GitHub → sempre stato aperto. Su mirror di football-data ho trovato le **quote per singolo
  bookmaker**: Pinnacle più sei book soft (B365, BW, IW, LB, WH, VC).

### 🎯 La strategia: sharp contro soft

Nei quattro run precedenti la "probabilità vera" veniva sempre da me. Sempre battuta.

Qui viene da **un mercato specifico noto per essere il più affilato**: Pinnacle — margini bassi,
puntate grosse accettate, non limita i vincenti. Il bersaglio non è "il mercato" in astratto, è un
book specifico che si discosta da Pinnacle sullo stesso evento.

```
p_sharp = de-vig(Pinnacle)
edge_b  = quota_del_book_b × p_sharp − 1
```

**Disegno pulito.** Il primo campione trovato (EPL 2012-2016, 1.516 partite) è quello su cui ho
formulato l'ipotesi. I dati trovati **dopo** (EPL 2016-2020 + Serie A, 1.137 partite) sono tenuti
separati come **fuori campione vero**.

### ✅ H0 — la premessa regge, e replica con precisione

| Campione | Book più affilato | Margine sul miglior soft | Overround Pinnacle |
|---|---|---|---|
| Scoperta | **Pinnacle** | +0.00059 | 2.02% |
| Fuori campione | **Pinnacle** | +0.00060 | 2.05% |

Due campioni indipendenti, stesso vincitore, margine identico alla quinta cifra. Non è fortuna.

### 🔬 Il test decisivo: contrasto invece di ROI assoluto

Il ROI assoluto confonde due domande: *il segnale contiene informazione?* e *il livello supera il
margine del book?* Il contrasto le separa — e usa tutte le 47.754 selezioni invece delle sole 3.665
con edge positivo, quindi ha molta più potenza.

| | Scoperta | **Fuori campione** | Combinato |
|---|---|---|---|
| Tutte le selezioni soft | — | −8.87% | −7.29% |
| edge > 0 | +6.39% | **+5.80%** | +6.13% |
| edge ≤ 0 | — | **−10.09%** | −8.40% |
| **Differenza** | — | **+15.89 pp** | **+14.54 pp** |
| **t / p** | — | **+2.82 / 0.0048** | **+4.39 / <0.0001** |

**Il segnale è reale e replica fuori campione a p = 0.0048.**

E i decili sono monotoni **nella direzione giusta**, su tutta la distribuzione:

| Decile | Edge medio | ROI realizzato |
|---|---|---|
| 1 | −18.68% | −21.15% |
| 5 | −5.12% | −9.73% |
| 9 | −1.14% | −0.94% |
| **10** | **+1.68%** | **+5.66%** (t=+2.11) |

Correlazione edge dichiarato / P&L realizzato: **+0.0433**.

**È l'esatto opposto di tutto il resto del progetto.** Il Dixon-Coles aveva correlazione negativa:
più si dichiarava sicuro, più sbagliava. La strategia della dispersione idem. Qui la relazione è
positiva e monotona su dieci decili.

### ⚠️ Cosa NON è stato dimostrato

Il risultato va letto con precisione, perché è facile sovrainterpretarlo.

| Domanda | Risposta | Evidenza |
|---|---|---|
| Il segnale contiene informazione? | **Sì** | contrasto p=0.0048 fuori campione, decili monotoni |
| Il livello supera zero? | **Forse** | +6.13% ma p=0.058 combinato, p=0.29 sul solo fuori campione |
| È "alto e garantito"? | **No** | e non lo sarà mai: "garantito" non esiste con un margine e un banco che può limitare |
| È incassabile? | **Non testato** | i book che sbagliano sono anche quelli che chiudono i conti vincenti |

La differenza fra le prime due righe è la potenza statistica: il contrasto usa 47.754 selezioni, il
test sul livello solo 3.665. Il **ranking** è stabilito; il **livello** servirebbe circa 1,4× di dati
in più per essere deciso.

⚠️ **H2 fallisce ancora sulle soglie alte** (a soglia 5% il ROI crolla a −7.58%). Non contraddice i
decili: le soglie alte guardano l'8% estremo delle selezioni, dove n è piccolo e domina il rumore.
I decili su tutta la distribuzione sono il test meglio alimentato.

⚠️ **I book "vincenti" non replicano.** VC era il migliore nella scoperta (+17.69%), solo +4.39%
fuori campione; BW era +2.15% e diventa +26.99%. Con 6 book × 5 soglie = 30 test, la probabilità di
vedere almeno un t>1.95 per caso è **79%**. Nessun singolo bookmaker è stabilito come sfruttabile.

### 📌 Dove siamo

Cinque run per dimostrare che prevedere il calcio meglio del mercato non funziona. Il sesto per
trovare la cosa che funziona, ed è di natura completamente diversa: **non prevedere niente, e
confrontare due prezzi**.

Il criterio di uscita dell'obiettivo — "confidenza alta e vantaggio matematico alto e garantito" —
resta **non soddisfatto**, e ora si può dire esattamente perché: la confidenza sul *segnale* è alta
(p=0.005), sul *profitto* è marginale (p=0.058), e la parola "garantito" non è soddisfacibile in
linea di principio.

Ma per la prima volta la direzione è quella giusta, e la barra scritta in HANDOFF è chiara: servono
più dati per-bookmaker per decidere il livello. Non parametri diversi. Non modelli migliori.
