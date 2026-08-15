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
| **2. Peer review anonimizzata** | Ogni membro riceve le risposte altrui **senza nomi** e le critica e classifica. Nessuno rivede sé stesso. | I modelli favoriscono il proprio output e lo stile della propria famiglia. Togliere le etichette rimuove quel bias |
| **3. Sintesi del Chairman** | Un modello designato legge tutte le risposte e tutte le classifiche e scrive il verdetto. | Serve qualcuno che prenda posizione sui disaccordi invece di mediarli |

Il punto che rende il protocollo utile non è la media delle opinioni: sono i **disaccordi**. Dove
due revisori si contraddicono, uno dei due sbaglia — ed è lì che si guarda.

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
