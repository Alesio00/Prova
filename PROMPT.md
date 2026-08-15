# PROMPT — versione migliorata + verdetto sul loop

## Verdetto sul gauntlet loop: **sì, ma solo nelle ultime 72 ore**

Un loop è efficiente quando *lo stato esterno cambia più in fretta di quanto costa ricontrollarlo*.
Qui lo stato è: quote, infortuni, formazioni, mercato aperto.

| Finestra | Cosa cambia davvero | Loop conviene? |
|---|---|---|
| Oggi → T−72h (15–21 ago) | Quasi niente. Qualche voce di mercato. | ❌ **No.** Un tick ogni ora rilegge le stesse pagine e brucia contesto per zero informazione. |
| T−72h → T−2h (21–24 ago) | Infortunati, mercato in chiusura (31 ago), quote che si muovono | ✅ **Sì**, ogni 6–12 h |
| T−2h → calcio d'inizio | **Formazioni ufficiali** — il singolo input più prezioso | ✅ **Sì**, ogni 15–30 min |
| Dopo il fischio finale | Il risultato: l'unico vero test del modello | ✅ **Un tick solo**, per registrare l'esito |

Quindi: non far girare un loop adesso. Programmalo per il 21 agosto.

```
/loop 8h  Aggiorna il modello Roma-Fiorentina. Rileggi HANDOFF.md e RESULTS.md.
Cerca SOLO cambiamenti: infortuni, squalifiche, movimenti di mercato, quote aggiornate,
formazioni. Se nulla è cambiato dall'ultimo tick, rispondi "nessun cambiamento" e fermati
senza toccare file. Se qualcosa è cambiato: aggiorna data/context.json (con _confidence e
_anchor), rilancia la pipeline, aggiungi un run a RESULTS.md con il delta in punti
percentuali rispetto al run precedente, rigenera il report. Da 2 ore prima del calcio
d'inizio passa a tick di 20 minuti finché non escono le formazioni ufficiali.
```

Le due clausole che rendono il loop economico invece che rumoroso: **"cerca solo cambiamenti"** e
**"se nulla è cambiato fermati senza toccare file"**. Senza quelle, ogni tick rifà tutto il lavoro.

---

## Prompt migliorato (riusabile per qualsiasi partita)

Cosa mancava all'originale, in concreto: non diceva cosa fare quando i dati non si trovano (ed è
esattamente quello che è successo — rete bloccata), non chiedeva di dichiarare l'incertezza, non
distingueva fra "il modello ha trovato valore" e "il modello concorda col mercato", e non fissava
nessun test di sanità. Aggiunti tutti e quattro.

```
Costruisci un modello predittivo per <SQUADRA CASA> – <SQUADRA OSPITE>, <COMPETIZIONE>,
<DATA E ORA>.

DATI — raccogli il più possibile: rating stagione precedente (GF/GA/punti), mercato estivo
in entrata e uscita, allenatore e modulo, formazioni probabili, infortuni e squalifiche,
precedenti, quote dei bookmaker, contesto (turno, meteo, riposo).
Scrivi tutto in un unico file di dati con, per ogni voce, un livello di confidenza e la
citazione della fonte. Se un dato non è recuperabile NON inventarlo: stimalo, marcalo come
stima e mettilo in un elenco "cosa non sappiamo".
Se un canale dati è bloccato, dillo subito, prosegui con quello che hai, e scrivi nel
handoff cosa andrebbe sbloccato e perché.

MODELLO — a strati, ognuno verificabile da solo:
1. Dixon-Coles (Poisson bivariata con correzione bassi punteggi) dalla forza delle squadre
2. Quote de-viggate come ancora bayesiana, non come verità
3. Fusione modello+mercato con log-opinion pooling, peso dichiarato
4. Monte Carlo con incertezza SUI PARAMETRI, non solo sull'esito — le λ sono stime
5. Layer ML (logistica + gradient boosting + random forest) con cross-validation e log loss
   contro un baseline di frequenza di classe
6. Analisi di sensibilità su ogni costante del modello

Retro-risolvi le λ dalla previsione fusa, così che 1X2, over/under, gol-gol, handicap e
risultato esatto siano coerenti fra loro per costruzione.
Tieni OGNI costante tunabile in cima a un solo modulo, con un commento sul perché di quel
valore. Nessun modulo deve inventare aggiustamenti propri.

ONESTÀ — dichiara esplicitamente cosa il layer ML aggiunge e cosa non aggiunge. Se è
addestrato su dati sintetici, è scaffolding e va detto. Se l'EV rispetto alle quote è dentro
l'incertezza del modello, la conclusione è "il mercato è efficiente, nessun valore trovato",
non un pronostico.

TEST DI SANITÀ — devono passare a ogni run, e mettili nel handoff:
- media Monte Carlo == λ analitica (entro 0.5%)
- |previsione ML − previsione analitica| < 5 pp
- somma matrice risultati esatti == 1
- log loss CV del ML < baseline di frequenza di classe

OUTPUT
- report HTML autonomo, light/dark, con: tile del risultato, confronto fra i metodi, heatmap
  dei risultati esatti, gol attesi e mercati derivati, marcatori, tornado di sensibilità,
  tabella EV, elenco di cosa non sappiamo
- RESULTS.md: tabella cosa-funziona / cosa-è-fragile / cosa-è-stato-scartato, inclusi i bug
  trovati e come sono stati trovati. Un run per sezione, con il delta rispetto al precedente.
- HANDOFF.md: come si esegue, mappa dei file, le costanti che governano tutto con il loro
  impatto misurato in punti percentuali, il grafo delle dipendenze, i test di sanità, e cosa
  fare per primo al prossimo giro.

STILE — risposte brevi e dirette. Scrivi codice quando c'è da scrivere codice, non
descrizioni di codice. Un numero senza la sua incertezza è un numero sbagliato.
```

## Cosa NON mettere nel prompt

- **"Predici il risultato esatto."** Il risultato singolo più probabile qui sta al 12.4%: qualunque
  pronostico secco è sbagliato ~88% delle volte anche a modello perfetto. Chiedi la distribuzione.
- **"Trova la scommessa di valore."** Chiedere un edge produce un edge, vero o no. Chiedi il
  confronto col mercato e lascia che la risposta possa essere "nessun valore" — che è la risposta
  giusta in questo caso.
- **"Usa più modelli ML possibile."** Su questo dataset la regressione logistica ha battuto sia
  gradient boosting sia random forest. Più capacità significa più overfitting del rumore, non più
  accuratezza.
