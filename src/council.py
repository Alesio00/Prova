"""LLM Council for this project, after karpathy/llm-council.

Karpathy's protocol has three stages:

  1. INDEPENDENT ANSWERS. The same question goes to every council member.
     Nobody sees anybody else's answer.
  2. ANONYMISED PEER REVIEW. Each member receives the others' answers with the
     identities stripped, then critiques and RANKS them. Anonymising is the
     whole trick: models favour their own output and their own family's style,
     and hiding the labels removes that.
  3. CHAIRMAN SYNTHESIS. One designated model reads every answer and every
     ranking and writes the final verdict.

Why it is worth the cost on a project like this one: a single model reviewing
its own work checks it against the same assumptions that produced it. Four of
the bugs in RESULTS.md were found by tests written before looking at the
result, not by re-reading code - which is exactly the blind spot a council is
supposed to cover.

TWO WAYS TO RUN IT
------------------

A. Through Claude Code subagents (what was actually used - no network needed).
   Spawn one agent per role with a different model, collect the transcripts,
   then run stage 2 and 3 on the pooled text. See COUNCIL.md for the prompts.

B. Through OpenRouter, like the original (needs egress, currently blocked).
   That is what this module implements. Set OPENROUTER_API_KEY and run:

       python3 council.py --question "..." --stage all

   Cross-vendor membership is the version worth having: a council drawn from
   one model family shares its family's blind spots, so its agreement is worth
   less than it looks. That limitation is stated plainly in COUNCIL.md.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import string
import urllib.error
import urllib.request
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"
ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"

# Cross-vendor by design. Swap freely - the protocol does not care which
# models sit on the council, only that they are not all the same one.
COUNCIL = [
    "anthropic/claude-opus-4.5",
    "openai/gpt-5.1",
    "google/gemini-3-pro",
    "x-ai/grok-4",
]
CHAIRMAN = "anthropic/claude-opus-4.5"


def _call(model: str, prompt: str, timeout: int = 180) -> str:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY non impostata")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
    }).encode()
    req = urllib.request.Request(
        ENDPOINT, data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            payload = json.load(r)
        return payload["choices"][0]["message"]["content"]
    except urllib.error.URLError as e:
        return f"[ERRORE {model}: {e}]"


def _anon_labels(n: int) -> list[str]:
    return [f"Risposta {string.ascii_uppercase[i]}" for i in range(n)]


def stage1(question: str, members: list[str] | None = None) -> dict[str, str]:
    """Independent answers. No member sees any other."""
    members = members or COUNCIL
    return {m: _call(m, question) for m in members}


def stage2(question: str, answers: dict[str, str],
           members: list[str] | None = None, seed: int = 0) -> dict[str, str]:
    """Anonymised peer review and ranking.

    Each member sees the others' answers under neutral labels, in an order
    shuffled per reviewer so position cannot stand in for identity. A member
    never reviews its own answer.
    """
    members = members or list(answers)
    rng = random.Random(seed)
    reviews = {}

    for reviewer in members:
        others = [(m, a) for m, a in answers.items() if m != reviewer]
        rng.shuffle(others)
        labels = _anon_labels(len(others))
        blocks = "\n\n".join(f"### {lab}\n{txt}" for lab, (_, txt) in
                             zip(labels, others))
        prompt = f"""Hai risposto a questa domanda:

{question}

Qui sotto ci sono le risposte di altri revisori, in forma anonima. Non sai chi
le ha scritte e non c'e la tua.

{blocks}

Il tuo compito:
1. Per ogni risposta, indica il punto piu forte e l'errore o la debolezza piu
   grave. Se un'affermazione e semplicemente falsa, dillo.
2. Segnala ogni punto su cui le risposte si CONTRADDICONO: sono i punti in cui
   qualcuno sbaglia, e sono i piu preziosi.
3. Classifica le risposte dalla migliore alla peggiore per accuratezza e
   solidita del ragionamento, motivando in una riga ciascuna.
4. Indica se qualcuna di queste risposte ti fa cambiare idea sulla tua, e su cosa.

Sii severo. L'accordo educato non serve a niente."""
        reviews[reviewer] = _call(reviewer, prompt)
        # the label map matters for auditing who said what afterwards
        reviews[f"_{reviewer}_labelmap"] = json.dumps(
            {lab: m for lab, (m, _) in zip(labels, others)})
    return reviews


def stage3(question: str, answers: dict[str, str], reviews: dict[str, str],
           chairman: str = CHAIRMAN) -> str:
    """Chairman synthesis over every answer and every ranking."""
    a_blocks = "\n\n".join(f"### {m}\n{t}" for m, t in answers.items())
    r_blocks = "\n\n".join(f"### Revisione di {m}\n{t}"
                           for m, t in reviews.items()
                           if not m.startswith("_"))
    prompt = f"""Sei il Chairman di un council di revisione. Domanda originale:

{question}

RISPOSTE INDIVIDUALI
{a_blocks}

REVISIONI INCROCIATE
{r_blocks}

Scrivi il verdetto finale. Regole:
- Parti dai punti su cui il council CONCORDA: sono i piu affidabili.
- Poi tratta i DISACCORDI uno per uno e prendi posizione, motivando. Non
  mediare fra due affermazioni quando una delle due e semplicemente falsa.
- Segnala esplicitamente ogni affermazione che un solo membro ha fatto e che
  nessun altro ha confermato: va trattata come non verificata.
- Chiudi con una raccomandazione operativa in tre righe al massimo.
- Scrivi per qualcuno che deve decidere, non per qualcuno che deve essere
  impressionato."""
    return _call(chairman, prompt)


def run(question: str, out: Path | None = None) -> dict:
    answers = stage1(question)
    reviews = stage2(question, answers)
    final = stage3(question, answers, reviews)
    result = {"question": question, "answers": answers,
              "reviews": reviews, "chairman_verdict": final}
    out = out or (RESULTS / "council_run.json")
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False),
                   encoding="utf-8")
    return result


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--question", required=True)
    ap.add_argument("--out", type=Path, default=None)
    args = ap.parse_args()
    r = run(args.question, args.out)
    print(r["chairman_verdict"])
