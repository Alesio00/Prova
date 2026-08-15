# Verbale del council — 2026-08-15

Due council distinti, con due protocolli diversi perché rispondono a due domande diverse.

---

## Council 1 — sul codice (quattro specialisti, quattro domande)

Quattro revisori indipendenti, modelli diversi, nessuno vede gli altri. Poi un arbitro riceve le
conclusioni anonimizzate e le verifica **eseguendo il codice**.

Lo stadio 2 dell'originale (classifica) non si applica qui: non si classificano risposte a domande
diverse. Sostituito da arbitrato incrociato.

### Convergenze (2+ revisori indipendenti) — tutte confermate

| Reperto | Verifica |
|---|---|
| L'inversione 1X2→λ fabbrica un'opinione sui gol che nessuna quota sostiene | Modello 2.4245 → fuso 2.6520 → mercato 2.8102. Over 2.5: 43.7% → 49.5% |
| Il totale pubblicato esce dalla banda del selfaudit stesso | p95 2.6389 < 2.6520 pubblicato |
| L'incertezza pubblicata è più stretta del vero | sd fusa 0.0187 contro sd modello 0.0377 |
| Numeri marcatori incoerenti fra i due motori | Confermato come fatto, **misdiagnosticato da entrambi**: è esattamente `p_available` |
| Nessun backtest, calibrazione mai dimostrata | `load_real_matches()` è un plug-in mai chiamato |

### Il meccanismo che nessun revisore aveva isolato

L'arbitro ha trovato la causa comune dei due reperti sull'incertezza: in `selfaudit.py` il vettore
mercato era `devig_shin(odds)` con **`odds` costante in tutte le 4.000 estrazioni**. Le quote non
avevano mai errore. Poiché il 60% del log-odds fuso veniva da un input a varianza zero, la sd del
fuso *doveva* essere circa metà di quella del modello: **artefatto aritmetico, non misura di
robustezza**. Per lo stesso motivo il "96.9% di disaccordo col mercato" era una tautologia.

### Un'accusa respinta

Due revisori segnalavano che Kean ha due probabilità diverse nello stesso file (24.2% e 20.9%).
Vero come fatto, sbagliato come diagnosi: `0.2422 × 0.85 = 0.2059`. È esattamente `p_available`,
applicato in un motore e non nell'altro. Difetto di **etichettatura**, non di calcolo.

### Un errore dell'arbitro, causato da me

L'arbitro ha dichiarato "cinque discrepanze su cinque inventate" e ha bollato un revisore come
"l'unico interamente non affidabile". **Sbagliato, e per colpa mia.** Le cinque stringhe esistevano
davvero nel commit `57b6b0d`, cioè lo stato che quel revisore aveva letto. Le ho corrette alle
12:25; l'arbitro è partito dopo e ha trovato i file già puliti.

> **Ho modificato gli artefatti sotto revisione mentre il protocollo era in corso.** È l'errore di
> processo più istruttivo di tutta la sessione: invalida il lavoro di un membro e produce
> un'accusa falsa contro di lui. Regola aggiunta a COUNCIL.md: durante un council i file sono
> congelati.

### Le tre correzioni prioritarie — applicate

| # | Problema | Correzione | Effetto misurato |
|---|---|---|---|
| 1 | Mercati gol pubblicati dall'inversione dell'1X2 | Pubblicati dalle λ del modello; il totale invertito resta ma etichettato "implicito dal mercato" | Over 2.5 **49.5% → 43.7%** |
| 2 | `goal_share × minutes/90` contava i minuti due volte | Tolto il fattore: `goal_share` è già una quota sull'intera partita (somma 1.02 / 1.075) | Castro **5.7% → 14.7%**, dal 7° al 4° posto. Cambia l'ordinamento |
| 3 | Quote come costante a varianza zero; `_verdict` sceglieva per P(EV>0) | Quote perturbate ±1.5%, metodo di de-vig campionato, selezione per dimensione dell'EV | Intervallo vero pubblicato accanto a quello fuso; selezione passa da 'draw' ad **'away'** |

Sul punto 3: `draw` batteva `away` di **0.7 pp contro un errore standard Monte Carlo di 0.76 pp** —
la selezione la decideva il seed.

### Nove falsi allarmi smontati

Il revisore statistico ha verificato e **respinto** i sospetti su: correzione τ di Dixon-Coles
(esatta da paper, normalizzazione = 1, marginali preservate), de-vig di Shin (converge a z=0.0229,
Σp = 1.00000000 prima della rinormalizzazione), `_draw_scores` (rejection sampler non distorto:
2M estrazioni, deviazione max 5.0e-4), `_assign_goals` (multinomiale vera), `log_pool`,
`solve_lambdas_for_probs` (ben identificato: converge da 7 punti di partenza a SSE ~1e-15),
lognormale a media preservata, doppio conteggio recency/squad_delta (già corretto), gestione dei seed.

---

## Council 2 — sulla decisione (tre membri, stessa domanda)

Qui il protocollo dell'originale si applica per intero: stessa domanda, classifica anonimizzata con
formato `FINAL RANKING`, aggregazione in posizione media.

### Aggregato

| Membro | Posizione media | Voti |
|---|---|---|
| **B (sonnet)** | **1.33** | 3 |
| A (opus) | 1.67 | 3 |
| C (haiku) | 3.00 | 3 |

C è ultimo **all'unanimità**.

### L'auto-valutazione, dichiarata

| Membro | Posizione che si è dato |
|---|---|
| A | 1ª |
| B | 1ª |
| C | 3ª |

Due membri su tre si sono messi primi nonostante l'anonimizzazione. Con tre soli membri questo pesa:
è il limite noto dell'inclusione di sé stessi, e va letto sapendolo. C, che si è messo ultimo, è
anche quello che ha commesso due errori fattuali arbitrando — quindi l'auto-valutazione onesta non
coincide con la qualità.

### Il disaccordo che contava, e come è stato risolto

Tre membri, tre fattori di rischio principali **diversi**. Un membro li ha messi sulla stessa scala
invece di discuterli:

| Fattore | Escursione dell'EV sulla Fiorentina a 6.40 |
|---|---|
| Kean (da certo a p=0.70) | 2.2 pp |
| Forma sotto Grosso (recency 0 → 0.73) | 6.2 pp |
| **λ della Roma** (1.44 → 1.97) | **15.5 pp** |

Ma un secondo membro ha dato una lettura diversa e complementare: λ della Roma a 1.85 è il **98.5°
percentile del suo stesso spazio parametrico**, quindi è un rischio in gran parte *già dentro* la
banda dichiarata. Kean è più piccolo ma **strutturalmente escluso**: nessuna banda lo misura.

**Sintesi**: λ della Roma è il rischio più grande in magnitudine e già parzialmente contabilizzato;
Kean è più piccolo ma interamente fuori dal modello. Non si escludono, si compongono.

### Un errore di arbitrato, verificato

Un membro ha contestato il "91% di EV positivo col modello puro" stimando ~75% con
un'approssimazione normale. **Misurato: 91.8%.** Aveva usato la deviazione standard di P(Roma)
(3.8 pp) al posto di quella di P(Fiorentina) (2.57 pp). Lo stesso membro affermava che solo un
revisore aveva notato il problema della forchetta dimezzata: falso, un altro lo dice apertamente e
dà pure il numero.

### Il reperto più tagliente

A ρ = 0 il mercato implica **esattamente** il totale del modello puro (2.430 contro 2.424). E la
divergenza col mercato non è distribuita: **λ Roma 1.599 contro 1.967 (23% di scarto), λ Fiorentina
0.826 contro 0.843 (2%)**.

La tesi del modello non è "la Fiorentina è sottovalutata". È **"la Roma segna 0.37 gol in meno di
quanto dica il prezzo"**. Due membri su tre hanno ripetuto la cornice sbagliata senza accorgersene —
e io prima di loro.

### Soglie di prezzo proposte

| Membro | Mercato | Soglia |
|---|---|---|
| A | Fiorentina +1.5 asiatico | ≥ 1.65 |
| B | Fiorentina 1X2 / X2 | ≥ 7.00 (X2 ≥ 2.15) |
| C | Fiorentina 1X2 | ≥ 6.80 |

Misurato: quota di break-even contro il p05 del modello puro = **6.67**. B è la più conservativa
perché usa il p05 della distribuzione *fusa* — cioè ancorata al prezzo contro cui scommette, la
stessa circolarità che B stessa denuncia. Innocua qui (6.88 contro 6.67).

A ha però scelto il mercato migliore: se il disaccordo è tutto su λ Roma, l'handicap è
**insensibile al difetto su ρ** che indebolisce over/under e totali.

---

## Verdetto del Chairman

**NESSUNA SCOMMESSA.** Regge a ogni correzione applicata, e per tre ragioni indipendenti che si
sommano invece di sovrapporsi:

1. **Kelly frazionario 0.11% e 0.05% del bankroll.** Non serve un audit a 4.000 estrazioni per non
   puntare un millesimo.
2. **Nessuna selezione supera la soglia di stabilità.** Dopo le correzioni: `away` 69.6% di EV
   positivo, 41.6% sopra il 5%. Serve ~85%.
3. **Zero backtest.** Un modello mai validato su una partita vera non ha una credibilità *misurata*,
   quindi non ha diritto a un peso contro un prezzo liquido. Il tasso di errore strutturale è noto e
   non piccolo: **cinque bug in quattro run**, uno da 9.3 pp.

Il rischio singolo non modellato (Kean) è più grande dell'intero edge dichiarato: propagandolo
nell'1X2, l'EV sulla Fiorentina a 6.40 scende da +1.2% verso lo zero.

**Cosa il council ha cambiato rispetto al verdetto precedente:** non la decisione, la sua
motivazione e tre numeri pubblicati. Over 2.5 era sbagliato di 5.8 pp, l'ordinamento dei marcatori
era sbagliato, e l'intervallo di incertezza era dimezzato per costruzione. Il "nessuna scommessa"
era giusto per caso più che per metodo.
