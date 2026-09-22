"""
Is the verification module right? An evaluation of the verifier itself.

    cd backend && OLLAMA_TEMPERATURE=0 python -m eval.verifier_eval          # ~10 min
    python -m eval.verifier_eval --limit 12                                    # smoke

The pipeline's last stage labels an answer verified or flags it. Every other suite measures the
answer; none measures that label. To measure it you need answers whose groundedness is KNOWN, so
they are built, not judged:

  correct               a real generated answer that contains the gold fact, with the gold evidence
                        in its context                                              -> should PASS
  fabricated_sentence   the same answer with one invented sentence inserted after its first sentence
                        (terms verified absent from the corpus: "eight A100 GPUs", "BLEU score of 41.2")
                                                                                    -> should FAIL
  fabricated_vague      the same, but the invented sentence has nothing checkable in it ("widely
                        regarded as the most popular choice")                       -> should FAIL
  number_swapped        the same answer with one figure that appears in the context changed to one
                        that does not                                               -> should FAIL
  wrong_document        a correct answer to a DIFFERENT question from a different document: fluent,
                        on-topic vocabulary, nothing to do with this context        -> should FAIL

Methods compared on identical cases:
  lexical   sentence-level lexical support only (>= 0.75 pass, <= 0.30 fail, else undecided)
  judge     the LLM judge on the full context (the original verifier)
  shipped   VerificationModule.verify_fast, exactly as the orchestrator calls it
"""
from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import re
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.text_support import lexical_support
from eval.metrics import contains_gold, evidence_rank
from eval.run_eval import RESULTS, _eval_db, load_jsonl

logger = logging.getLogger("verifier_eval")

CLASSES = ("correct", "fabricated_sentence", "fabricated_vague", "number_swapped", "wrong_document")
SHOULD_PASS = {"correct": True, "fabricated_sentence": False, "fabricated_vague": False, "number_swapped": False, "wrong_document": False}

# Each contains at least one term the corpus never uses (tests/test_verifier_eval.py checks that).
FABRICATIONS = [
    "The system was benchmarked on a cluster of eight A100 GPUs.",
    "It achieved a BLEU score of 41.2 on the held-out set.",
    "Deployment is managed with Kubernetes across three availability zones.",
    "User accounts are stored in a PostgreSQL 15 database.",
    "Voice queries are transcribed with Whisper before retrieval.",
    "Every request is authenticated with a JWT that expires after 30 minutes.",
    "The project is released under the Apache license.",
    "An nginx reverse proxy terminates TLS in front of the backend.",
]
# Invented, but with nothing checkable in them: no figure, identifier or name. The specifics check
# cannot catch these by design; they are here so the evaluation shows that limit instead of hiding it.
VAGUE_FABRICATIONS = [
    "It is widely regarded as the most popular choice among enterprise developers.",
    "Most reviewers found this approach considerably easier to maintain over time.",
    "This design was later adopted by several other university teams.",
    "Early users reported that it noticeably improved their daily workflow.",
]
FABRICATION_ABSENT_TERMS = ["a100", "bleu", "kubernetes", "postgres", "whisper", "jwt", "apache", "nginx"]

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")
_NUM = re.compile(r"(?<![\w.])(\d{2,}(?:[.,]\d+)?|\d\.\d+)(?![\w])")


def trim_to_sentence(text: str) -> str:
    """Stored answers may be cut mid-sentence; keep whole sentences only."""
    text = (text or "").strip()
    cut = max(text.rfind(". "), text.rfind(".\n"), text.rfind("]\n"))
    if text.endswith((".", "!", "?", "]")) or cut == -1:
        return text
    return text[: cut + 1].strip()


def insert_fabrication(answer: str, k: int, pool: list[str] | None = None) -> str:
    pool = pool or FABRICATIONS
    parts = _SENT_SPLIT.split(answer.strip(), maxsplit=1)
    fab = pool[k % len(pool)]
    return f"{parts[0]} {fab} {parts[1]}" if len(parts) == 2 else f"{parts[0]} {fab}"


def swap_number(answer: str, context_text: str) -> str | None:
    """Change the first multi-digit/decimal number in the answer that the context also contains to
    one the context does not contain. None if the answer has no such number."""
    for m in _NUM.finditer(answer):
        raw = m.group(1)
        if raw not in context_text:
            continue
        value = float(raw.replace(",", ""))
        for factor in (1.35, 1.7, 0.6, 2.4):
            new = value * factor
            repl = f"{new:.1f}" if "." in raw and "," not in raw else str(int(round(new)))
            if repl != raw and repl not in context_text and repl not in answer:
                return answer[: m.start(1)] + repl + answer[m.end(1):]
    return None


def build_cases(base: list[dict]) -> list[dict]:
    """base rows: {id, source, answer, context:[...], gold_evidence}. Deterministic: no randomness."""
    cases = []
    for k, r in enumerate(base):
        ctx_text = "\n".join(r["context"])
        cases.append({"id": r["id"], "class": "correct", "answer": r["answer"], "context": r["context"]})
        cases.append({"id": r["id"], "class": "fabricated_sentence", "answer": insert_fabrication(r["answer"], k), "context": r["context"]})
        cases.append({"id": r["id"], "class": "fabricated_vague", "answer": insert_fabrication(r["answer"], k, VAGUE_FABRICATIONS), "context": r["context"]})
        swapped = swap_number(r["answer"], ctx_text)
        if swapped:
            cases.append({"id": r["id"], "class": "number_swapped", "answer": swapped, "context": r["context"]})
        # a correct answer to another question, from another document, whose evidence this context lacks
        for j in range(1, len(base)):
            other = base[(k + j) % len(base)]
            if other["source"] != r["source"] and evidence_rank(other["gold_evidence"], r["context"]) is None:
                cases.append({"id": r["id"], "class": "wrong_document", "answer": other["answer"], "context": r["context"], "from": other["id"]})
                break
    return cases


def lexical_verdict(support: float, hi: float = 0.75, lo: float = 0.30) -> bool | None:
    return True if support >= hi else False if support <= lo else None


def summarize(rows: list[dict], methods: tuple[str, ...]) -> dict:
    out = {}
    for cls in CLASSES:
        sub = [r for r in rows if r["class"] == cls]
        if not sub:
            continue
        d = {"n": len(sub), "should_pass": SHOULD_PASS[cls], "mean_support": round(sum(r["support"] for r in sub) / len(sub), 3)}
        for m in methods:
            vals = [r[m] for r in sub]
            passed = sum(1 for v in vals if v is True)
            d[m] = {"pass": passed, "fail": sum(1 for v in vals if v is False), "undecided": sum(1 for v in vals if v is None),
                    "correct_rate": round((passed if SHOULD_PASS[cls] else sum(1 for v in vals if v is False)) / len(sub), 3)}
        out[cls] = d
    return out


def format_table(summary: dict, methods: tuple[str, ...]) -> str:
    head = "| answer class | n | truth | mean lexical support | " + " | ".join(f"{m}: right verdict" for m in methods) + " |"
    lines = [head, "|---|---|---|---|" + "---|" * len(methods)]
    for cls, d in summary.items():
        cells = []
        for m in methods:
            x = d[m]
            und = f", {x['undecided']} undecided" if x["undecided"] else ""
            cells.append(f"**{x['correct_rate']:.2f}** ({x['pass']} pass / {x['fail']} fail{und})")
        lines.append(f"| {cls} | {d['n']} | should {'PASS' if d['should_pass'] else 'FAIL'} | {d['mean_support']:.2f} | " + " | ".join(cells) + " |")
    return "\n".join(lines)


async def make_base(limit: int | None, model_choice: str) -> list[dict]:
    from models.generation import GenerationModel
    from retrieval.reranker import RerankerModel
    db, gen, reranker = _eval_db(), GenerationModel(), RerankerModel()
    base = []
    for q in load_jsonl("qa.jsonl", limit):
        docs = db.hybrid_retrieve(q["question"], top_k=10)
        texts = [d.page_content for d in docs]
        srcs = [d.metadata.get("source", "?") for d in docs]
        context = reranker.rerank(q["question"], texts, top_k=5)
        if evidence_rank(q["gold_evidence"], context) is None:
            continue
        answer = trim_to_sentence(await gen.generate_answer(q["question"], context, sources=srcs[:len(context)], mode="analytical", model_choice=model_choice))
        if contains_gold(answer, q["gold_answer"]):
            base.append({"id": q["id"], "source": q["source"], "answer": answer, "context": context, "gold_evidence": q["gold_evidence"]})
            logger.info(f"{q['id']}: usable correct answer ({len(answer)} chars)")
    return base


async def judge_all(cases: list[dict], model_choice: str, extra_methods: dict | None = None) -> list[dict]:
    from verification.verifier import VerificationModule
    v = VerificationModule()
    calls = {"n": 0}
    real_invoke = v.llm.invoke
    def counting_invoke(*a, **k):
        calls["n"] += 1
        return real_invoke(*a, **k)
    v.llm.invoke = counting_invoke
    rows = []
    for c in cases:
        support = lexical_support(c["answer"], c["context"])
        t0 = time.perf_counter(); judge_ok, judge_reason = await v.verify(c["answer"], c["context"], model_choice=model_choice); t_judge = time.perf_counter() - t0
        before = calls["n"]; t0 = time.perf_counter(); ship_ok, ship_reason = await v.verify_fast(c["answer"], c["context"], model_choice=model_choice); t_ship = time.perf_counter() - t0
        row = {"id": c["id"], "class": c["class"], "support": round(support, 3), "lexical": lexical_verdict(support),
               "judge": bool(judge_ok), "judge_reason": judge_reason[:160], "judge_s": round(t_judge, 2),
               "shipped": bool(ship_ok), "shipped_reason": ship_reason[:200], "shipped_s": round(t_ship, 2),
               "shipped_used_llm": calls["n"] > before, "answer": c["answer"][:400]}
        for name, fn in (extra_methods or {}).items():
            row[name] = fn(c["answer"], c["context"])
        rows.append(row)
        logger.info(f"{c['id']} {c['class']:20} support={support:.2f} judge={'P' if judge_ok else 'F'} shipped={'P' if ship_ok else 'F'}")
    return rows


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--model", default="auto")
    ap.add_argument("--label", default="verifier")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "sentence_transformers", "faiss", "urllib3", "retrieval", "models", "core", "verification"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
    t0 = time.time()
    base = asyncio.run(make_base(args.limit, args.model))
    cases = build_cases(base)
    rows = asyncio.run(judge_all(cases, args.model))
    methods = ("lexical", "judge", "shipped")
    summary = summarize(rows, methods)
    table = format_table(summary, methods)
    llm_share = sum(r["shipped_used_llm"] for r in rows) / max(1, len(rows))
    extra = (f"\n\nshipped verifier consulted the model on {llm_share:.0%} of cases; mean seconds per verdict: "
             f"judge {sum(r['judge_s'] for r in rows) / max(1, len(rows)):.1f}, shipped {sum(r['shipped_s'] for r in rows) / max(1, len(rows)):.1f}; "
             f"temperature {os.getenv('OLLAMA_TEMPERATURE', 'default (sampled)')}")
    out = {"config": vars(args), "temperature": os.getenv("OLLAMA_TEMPERATURE"), "started": datetime.now().isoformat(timespec="seconds"),
           "elapsed_s": round(time.time() - t0, 1), "base_answers": len(base), "summary": summary, "rows": rows}
    os.makedirs(RESULTS, exist_ok=True)
    path = os.path.join(RESULTS, f"verifier_{args.label}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(out, f, indent=2, ensure_ascii=False)
    # Full answers and contexts, so a deterministic rule can be re-examined offline in seconds
    # instead of a ten-minute run. (results/ is git-ignored.)
    with open(path.replace("verifier_", "verifier_cases_", 1), "w", encoding="utf-8") as f:
        json.dump(cases, f, ensure_ascii=False)
    with open(os.path.join(RESULTS, "history.md"), "a", encoding="utf-8") as f:
        f.write(f"\n### verifier evaluation {args.label} — {out['started']} ({out['elapsed_s']}s, {len(base)} base answers)\n\n{table}{extra}\n")
    print("\n" + table + extra + f"\n\nwrote {path}")


if __name__ == "__main__":
    main()
