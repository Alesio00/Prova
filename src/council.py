"""LLM Council — port fedele di karpathy/llm-council a questo progetto.

Scritto leggendo il sorgente vero (backend/council.py, backend/config.py), non
una ricostruzione da descrizioni di terzi. Una prima versione di questo file era
ricostruita da snippet di ricerca e aveva tre differenze dall'originale, due
delle quali erano invenzioni mie. Sono documentate in fondo, perche sapere dove
si e deviato da una fonte vale piu che fingere di non averlo fatto.

I TRE STADI (come nell'originale)
---------------------------------
1. Prime opinioni      - la stessa domanda a ogni membro, in parallelo
2. Review              - ogni membro riceve TUTTE le risposte anonimizzate
                         (inclusa la propria) e le classifica
3. Risposta finale     - un Chairman sintetizza risposte + classifiche

Il pezzo che rende il protocollo misurabile, e che la mia prima versione non
aveva affatto, e il formato di output vincolato:

    FINAL RANKING:
    1. Response C
    2. Response A

parsato con regex e aggregato in una posizione media per modello. Senza quello
il council produce quattro opinioni e nessun verdetto.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"

# Cross-vendor per costruzione: e il punto del council. Membri tutti della
# stessa famiglia condividono i punti ciechi della famiglia.
COUNCIL_MODELS = [
    "openai/gpt-5.1",
    "google/gemini-3-pro-preview",
    "anthropic/claude-sonnet-4.5",
    "x-ai/grok-4",
]
CHAIRMAN_MODEL = "google/gemini-3-pro-preview"


# --------------------------------------------------------------------------
# trasporto
# --------------------------------------------------------------------------

def _query_sync(model: str, prompt: str, timeout: float = 180.0) -> str | None:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY non impostata")
    body = json.dumps({"model": model,
                       "messages": [{"role": "user", "content": prompt}]}).encode()
    req = urllib.request.Request(
        OPENROUTER_API_URL, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.load(r)["choices"][0]["message"]["content"]
    except (urllib.error.URLError, KeyError, TimeoutError):
        return None


async def query_models_parallel(models: list[str], prompt: str) -> dict[str, str | None]:
    """Tutti i membri in parallelo. Un membro che fallisce viene escluso, non
    fa fallire il council."""
    async def one(m):
        return m, await asyncio.to_thread(_query_sync, m, prompt)
    return dict(await asyncio.gather(*(one(m) for m in models)))


# --------------------------------------------------------------------------
# stadio 1
# --------------------------------------------------------------------------

async def stage1_collect_responses(user_query: str,
                                   models: list[str] | None = None) -> list[dict]:
    models = models or COUNCIL_MODELS
    responses = await query_models_parallel(models, user_query)
    return [{"model": m, "response": r} for m, r in responses.items() if r]


# --------------------------------------------------------------------------
# stadio 2
# --------------------------------------------------------------------------

RANKING_TEMPLATE = """Stai valutando risposte diverse alla seguente domanda:

Domanda: {query}

Qui sotto le risposte di modelli diversi, in forma anonima:

{responses}

Il tuo compito:
1. Valuta ogni risposta singolarmente. Per ognuna, spiega cosa fa bene e cosa fa male.
2. Segnala ogni punto su cui le risposte si CONTRADDICONO: sono i punti in cui qualcuno sbaglia, e sono i piu preziosi.
3. Alla fine, e solo alla fine, dai la classifica finale.

IMPORTANTE: la classifica finale DEVE essere formattata ESATTAMENTE cosi:
- Inizia con la riga "FINAL RANKING:" (maiuscolo, con i due punti)
- Poi elenca le risposte dalla migliore alla peggiore, lista numerata
- Ogni riga: numero, punto, spazio, e SOLO l'etichetta (es. "1. Response A")
- Nessun altro testo dentro la sezione della classifica

Esempio del formato corretto per la TUA INTERA risposta:

Response A da buon dettaglio su X ma manca Y...
Response B e accurata ma superficiale su Z...
Response C offre la risposta piu completa...

FINAL RANKING:
1. Response C
2. Response A
3. Response B

Ora valuta e classifica:"""


def build_labels(stage1_results: list[dict]) -> tuple[str, dict[str, str]]:
    """Etichette anonime e mappa etichetta->modello per l'audit a valle."""
    labels = [chr(65 + i) for i in range(len(stage1_results))]
    text = "\n\n".join(f"Response {lab}:\n{r['response']}"
                       for lab, r in zip(labels, stage1_results))
    label_to_model = {f"Response {lab}": r["model"]
                      for lab, r in zip(labels, stage1_results)}
    return text, label_to_model


async def stage2_collect_rankings(user_query: str, stage1_results: list[dict],
                                  models: list[str] | None = None):
    models = models or COUNCIL_MODELS
    responses_text, label_to_model = build_labels(stage1_results)
    prompt = RANKING_TEMPLATE.format(query=user_query, responses=responses_text)
    responses = await query_models_parallel(models, prompt)
    out = [{"model": m, "ranking": t, "parsed_ranking": parse_ranking_from_text(t)}
           for m, t in responses.items() if t]
    return out, label_to_model


def parse_ranking_from_text(ranking_text: str) -> list[str]:
    """Estrae la sezione FINAL RANKING. Con fallback progressivi, perche un
    modello che sbaglia il formato non deve far perdere il suo voto."""
    if "FINAL RANKING:" in ranking_text:
        section = ranking_text.split("FINAL RANKING:")[1]
        numbered = re.findall(r"\d+\.\s*Response [A-Z]", section)
        if numbered:
            return [re.search(r"Response [A-Z]", m).group() for m in numbered]
        return re.findall(r"Response [A-Z]", section)
    return re.findall(r"Response [A-Z]", ranking_text)


def calculate_aggregate_rankings(stage2_results: list[dict],
                                 label_to_model: dict[str, str]) -> list[dict]:
    """Posizione media di ogni modello attraverso tutte le classifiche.

    E' l'unico output quantitativo del protocollo: trasforma quattro opinioni
    in un ordinamento.
    """
    positions = defaultdict(list)
    for r in stage2_results:
        for pos, label in enumerate(r["parsed_ranking"], start=1):
            if label in label_to_model:
                positions[label_to_model[label]].append(pos)
    agg = [{"model": m, "average_rank": round(sum(p) / len(p), 2),
            "rankings_count": len(p)} for m, p in positions.items() if p]
    agg.sort(key=lambda x: x["average_rank"])
    return agg


# --------------------------------------------------------------------------
# stadio 3
# --------------------------------------------------------------------------

CHAIRMAN_TEMPLATE = """Sei il Chairman di un LLM Council. Piu modelli hanno risposto alla domanda di un utente, poi hanno classificato le risposte l'uno dell'altro.

Domanda originale: {query}

STADIO 1 - Risposte individuali:
{stage1}

STADIO 2 - Classifiche incrociate:
{stage2}

Il tuo compito e sintetizzare tutto questo in una risposta unica, completa e accurata. Considera:
- Le risposte individuali e le loro intuizioni
- Le classifiche e cosa rivelano sulla qualita delle risposte
- Ogni schema di accordo o disaccordo

Regole aggiuntive, che l'originale lascia implicite e che qui servono perche il
council sta arbitrando decisioni e non opinioni:
- Parti dai punti su cui il council CONCORDA: sono i piu affidabili.
- Sui DISACCORDI prendi posizione e motiva. Non mediare fra due affermazioni quando una e semplicemente falsa.
- Segnala ogni affermazione fatta da un solo membro e non confermata da altri: e non verificata, e va detto.

Scrivi per qualcuno che deve decidere, non per qualcuno che deve essere impressionato."""


async def stage3_synthesize_final(user_query: str, stage1_results: list[dict],
                                  stage2_results: list[dict],
                                  chairman: str = CHAIRMAN_MODEL) -> dict:
    stage1_text = "\n\n".join(f"Model: {r['model']}\nResponse: {r['response']}"
                              for r in stage1_results)
    stage2_text = "\n\n".join(f"Model: {r['model']}\nRanking: {r['ranking']}"
                              for r in stage2_results)
    prompt = CHAIRMAN_TEMPLATE.format(query=user_query, stage1=stage1_text,
                                      stage2=stage2_text)
    text = await asyncio.to_thread(_query_sync, chairman, prompt)
    return {"model": chairman,
            "response": text or "Errore: sintesi finale non generata."}


# --------------------------------------------------------------------------

async def run_full_council(user_query: str) -> dict:
    stage1 = await stage1_collect_responses(user_query)
    if not stage1:
        return {"error": "nessun modello ha risposto"}
    stage2, label_to_model = await stage2_collect_rankings(user_query, stage1)
    aggregate = calculate_aggregate_rankings(stage2, label_to_model)
    stage3 = await stage3_synthesize_final(user_query, stage1, stage2)
    return {"question": user_query, "stage1": stage1, "stage2": stage2,
            "stage3": stage3,
            "metadata": {"label_to_model": label_to_model,
                         "aggregate_rankings": aggregate}}


# --------------------------------------------------------------------------
# DIFFERENZE DALL'ORIGINALE, dichiarate
# --------------------------------------------------------------------------
#
# 1. Un membro classifica ANCHE la propria risposta. Nell'originale e cosi, ed
#    e corretto: l'anonimizzazione e il meccanismo che impedisce di favorirsi,
#    non l'esclusione. La mia prima versione escludeva il se stesso, il che
#    toglie un voto a ogni classifica senza aggiungere protezione.
#
# 2. L'ordine delle etichette e lo stesso per tutti i revisori. La mia prima
#    versione lo mescolava per revisore. E' una difesa in piu contro il bias di
#    posizione, ma rompe l'aggregazione dell'originale (le posizioni medie non
#    sarebbero piu confrontabili senza rimappare) e non e nel protocollo.
#    Tolta: si segue la fonte.
#
# 3. Il parsing di FINAL RANKING e l'aggregazione in posizione media non
#    esistevano affatto nella mia prima versione. Sono il pezzo che trasforma
#    il council da "quattro opinioni" a "un ordinamento", e ometterli era la
#    lacuna piu grave.
#
# UNA DIFFERENZA DI DISEGNO CHE RESTA, e che va capita prima di usare questo file
# -----------------------------------------------------------------------------
# Nell'originale tutti i membri rispondono ALLA STESSA domanda, ed e per questo
# che classificarsi a vicenda ha senso. Il council sul CODICE eseguito in questo
# progetto era diverso: quattro specialisti con quattro domande diverse
# (correttezza statistica, scelte di modellazione, verifica dei fatti, analisi
# decisionale). Su un council cosi lo stadio 2 dell'originale NON si applica -
# non si classificano risposte a domande diverse - e va sostituito da un
# arbitrato incrociato. Il protocollo con classifica e aggregazione vale per la
# domanda decisionale, dove tutti rispondono alla stessa cosa.


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="LLM Council (karpathy/llm-council)")
    ap.add_argument("--question", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    result = asyncio.run(run_full_council(args.question))
    (args.out or RESULTS / "council_run.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(result.get("metadata", {}).get("aggregate_rankings", []),
                     indent=2))
    print("\n" + result.get("stage3", {}).get("response", ""))
