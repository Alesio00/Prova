# LLM Council — protocollo

Adattamento di [karpathy/llm-council](https://github.com/karpathy/llm-council) a questo progetto.

## Perché serviva

Fino al run 003 tutta la revisione è stata fatta da un solo modello: quello che ha scritto il
codice. I quattro bug trovati nei run precedenti sono usciti da **test scritti prima di guardare il
risultato**, non dal rileggere il codice — perché rileggere il proprio codice lo controlla contro le
stesse assunzioni che l'hanno prodotto. Quello è esattamente il punto cieco che un council copre.

## I tre stadi

| Stadio | Cosa succede | Perché |
|---|---|---|
| **1. Risposte indipendenti** | La stessa domanda va a ogni membro. Nessuno vede le risposte degli altri. | Evita l'ancoraggio: il primo parere non contamina gli altri |
| **2. Peer review anonimizzata** | Ogni membro riceve **tutte** le risposte senza nomi — inclusa la propria — e le classifica in un formato vincolato | I modelli favoriscono il proprio output. È **l'anonimizzazione** a impedirlo, non l'esclusione |
| **3. Sintesi del Chairman** | Un modello designato legge tutte le risposte e tutte le classifiche e scrive il verdetto. | Serve qualcuno che prenda posizione sui disaccordi invece di mediarli |

Il pezzo che rende il protocollo **misurabile** è il formato di output vincolato dello stadio 2:

```
FINAL RANKING:
1. Response C
2. Response A
```

parsato con regex e aggregato in una **posizione media per modello**. Senza quello il council
produce quattro opinioni e nessun verdetto.

Il punto che lo rende **utile** è un altro: non la media delle opinioni, ma i **disaccordi**. Dove
due revisori si contraddicono, uno dei due sbaglia — ed è lì che si guarda.

## Cosa avevo sbagliato ricostruendolo

La prima versione di `src/council.py` era ricostruita da snippet di ricerca invece che dal sorgente.
Aveva tre differenze dall'originale, due delle quali erano invenzioni mie:

| # | La mia versione | L'originale | Verdetto |
|---|---|---|---|
| 1 | Un membro non rivedeva sé stesso | Rivede anche sé stesso, anonimizzato | **Sbagliavo io.** L'anonimizzazione è già la protezione; escludersi toglie un voto senza aggiungere niente |
| 2 | Ordine delle risposte mescolato per revisore | Stesso ordine per tutti | **Deviazione mia.** Difende dal bias di posizione ma rompe l'aggregazione delle posizioni medie. Tolta |
| 3 | — | Parsing di `FINAL RANKING` + posizione media aggregata | **Lacuna grave.** È il pezzo che trasforma il council da quattro opinioni a un ordinamento. Non c'era affatto |

Il sorgente è `backend/council.py` in [karpathy/llm-council](https://github.com/karpathy/llm-council).
Vale la pena leggerlo: sono ~250 righe.

## Una differenza di disegno che resta

Nell'originale **tutti i membri rispondono alla stessa domanda** — ed è per questo che classificarsi
a vicenda ha senso.

Il council sul **codice** eseguito qui era diverso: quattro specialisti con quattro domande diverse
(correttezza statistica, scelte di modellazione, verifica dei fatti, analisi decisionale). Su un
council così **lo stadio 2 dell'originale non si applica**: non si classificano risposte a domande
diverse. Va sostituito da un *arbitrato incrociato* — un membro riceve tutte le conclusioni
anonimizzate e deve trovare convergenze, contraddizioni e affermazioni non confermate.

Il protocollo con classifica e aggregazione vale per la **domanda decisionale**, dove tutti
rispondono alla stessa cosa. Sono due usi diversi dello stesso schema, e confonderli produce una
classifica priva di significato.

## Come è stato eseguito qui

Tramite subagent di Claude Code, uno per ruolo, con modelli diversi. Nessuna rete richiesta.

| Ruolo | Cosa cerca |
|---|---|
| **Correttezza statistica** | errori matematici, doppi conteggi, circolarità, bug silenziosi. Può eseguire il codice per confermare |
| **Scelte di modellazione** | assunzioni sbagliate, dati inaffidabili, cosa manca del tutto |
| **Verifica dei fatti interni** | ogni numero nei documenti confrontato con quello che il codice produce davvero |
| **Analisi decisionale** | legge solo i risultati e arriva alla propria conclusione, senza affetto per le scelte del modello |

I primi tre formano il council sul codice, il quarto quello sulla decisione. Poi stadio 2 e 3 sul
pool comune.

## Il limite di questo council, dichiarato

**È un council monofamiliare.** Karpathy mette insieme modelli di fornitori diversi (GPT, Gemini,
Claude, Grok) proprio perché i punti ciechi non siano correlati. Qui i membri sono tutti Claude, con
modelli e livelli di ragionamento diversi ma con lo stesso addestramento di base. Conseguenza
concreta: **quando questo council è d'accordo, quell'accordo vale meno di quanto sembri.** I
disaccordi restano informativi; l'unanimità no.

L'egress di rete è bloccato in questo ambiente, quindi la versione cross-vendor non era eseguibile.

## Rieseguirlo

**Via subagent** (quello che è stato fatto): i prompt dei quattro ruoli sono qui sopra; lanciali con
modelli diversi, raccogli le risposte, poi passa allo stadio 2 con le identità rimosse.

**Via OpenRouter** (come l'originale, richiede rete): `src/council.py` implementa i tre stadi.

```bash
export OPENROUTER_API_KEY=...
cd src && python3 council.py --question "..."
```

Membri e Chairman si cambiano in cima al file. Lo stadio 2 mescola l'ordine delle risposte per ogni
revisore, così la posizione non fa da sostituto dell'identità, e salva la mappa etichetta→modello
per poter ricostruire chi ha detto cosa a valle.

## Esito del primo run

Vedi `results/council.md`.
