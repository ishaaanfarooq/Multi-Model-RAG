"""
Unsupported specifics: the concrete things an answer asserts that its sources never mention.

Sentence-level lexical support asks "are most of this sentence's words in the sources?". That
misses exactly the hallucinations that matter most: a changed figure leaves every other word
supported, and one invented sentence barely moves the average of a long answer. Measured
(eval/VERIFIER.md): 29% of answers with an invented sentence, and 4 of 6 with a changed number,
were passed.

A *specific* is a token that is either checkable or nothing:
  - a number with two or more digits, or a decimal   (1000, 41.2, 78.4 - not "3", not the citation [2])
  - an identifier-like term: has a digit and a letter (A100, qwen2.5), is ALL CAPS (BLEU, JWT),
    or has an internal capital (PostgreSQL, FastAPI)
  - a capitalised word that does not start its sentence (Kubernetes, Whisper)
It is supported when the sources contain it, case-insensitively. Anything else is left to the
other checks: this one is deliberately narrow so that a hit means something.
"""
from __future__ import annotations

import re

_CITATION = re.compile(r"\[(?:source\s*)?\d+(?:\s*,\s*\d+)*\]|\(from:[^)]*\)", re.I)
_HEADER_LINE = re.compile(r"^\s{0,3}#{1,6}\s.*$", re.M)
_LIST_MARK = re.compile(r"^\s*(?:[-*•]|\d{1,2}[.)])\s+", re.M)
_SENT_SPLIT = re.compile(r"(?<=[.!?:])\s+|\n+|\s+[-–—]\s+")   # a spaced dash after a list label starts a new clause
_NUMBER = re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?%?(?![\w])")
_WORD = re.compile(r"[A-Za-z][A-Za-z0-9]*(?:[.\-_/][A-Za-z0-9]+)*")

# Capitalised mid-sentence words that are prose, not entities.
_COMMON = {"i", "ai", "ok", "the", "a", "an", "however", "therefore", "additionally", "furthermore", "moreover",
           "according", "source", "sources", "context", "answer", "summary", "note", "overall", "yes", "no",
           "direct", "detailed", "analysis", "key", "points", "conclusion", "in", "this", "these", "it", "its",
           # document-structure words, routinely capitalised in prose ("in Section 3.1", "the Retrieval Layer")
           "section", "chapter", "figure", "table", "step", "phase", "tier", "layer", "module", "part", "appendix"}


# Ubiquitous computing vocabulary. Describing a FastAPI server as serving "HTTP", or an RTX card as
# a "GPU", is wording, not a claim the sources must contain; flagging it produced warnings that named
# 'GPU' (both real false alarms from the evaluation). Deliberately short: anything that could be a
# project-specific choice (JWT, TLS, BLEU, CUDA, AWS, ...) is NOT here and is still checked.
_GENERIC_ACRONYMS = {"ai", "ml", "llm", "llms", "nlp", "api", "apis", "url", "urls", "http", "https", "html", "json",
                     "pdf", "pdfs", "csv", "cpu", "cpus", "gpu", "gpus", "ram", "os", "ui", "ux", "id", "ids", "io", "faq"}


def _clean(answer: str) -> str:
    text = _CITATION.sub(" ", answer or "")
    text = _HEADER_LINE.sub(" ", text)
    text = _LIST_MARK.sub("", text)
    return text.replace("**", "").replace("__", "").replace("`", "")


def _is_number_specific(tok: str) -> bool:
    digits = re.sub(r"\D", "", tok)
    return len(digits) >= 2 or "." in tok.rstrip(".")


def _is_identifier(word: str) -> bool:
    has_digit, has_alpha = any(c.isdigit() for c in word), any(c.isalpha() for c in word)
    if has_digit and has_alpha:
        return True
    letters = [c for c in word if c.isalpha()]
    if len(letters) >= 2 and all(c.isupper() for c in letters):
        return True                                           # BLEU, JWT, FAISS
    return any(c.isupper() for c in word[1:]) and any(c.islower() for c in word)   # PostgreSQL, FastAPI


def _is_capitalised(word: str) -> bool:
    return len(word) >= 2 and word[0].isupper() and word[1:].islower()


def extract_specifics(answer: str) -> list[str]:
    """Checkable tokens in the answer, in order of appearance, without duplicates."""
    found, seen = [], set()
    offset = 0
    hits: list[tuple[int, str]] = []
    for sentence in _SENT_SPLIT.split(_clean(answer)):
        sentence = sentence.strip()
        if not sentence:
            continue
        for m in _NUMBER.finditer(sentence):
            tok = m.group(0).rstrip(".,")
            if _is_number_specific(tok):
                hits.append((offset + m.start(), tok))
        words = list(_WORD.finditer(sentence))
        for idx, m in enumerate(words):
            w = m.group(0).strip(".-_/")
            if len(w) < 2 or w.lower() in _COMMON or w.lower() in _GENERIC_ACRONYMS:
                continue
            if _is_identifier(w):
                hits.append((offset + m.start(), w))
            elif idx > 0 and _is_capitalised(w) and len(w) >= 4:
                # Capitalised and not sentence-initial. Skip Title Case runs ("Large Language Models",
                # "Convolutional Neural Networks", "**Information Staleness**"): they are usually a label
                # or the expansion of an acronym the sources do use, not a named thing.
                prev_w = words[idx - 1].group(0)
                next_w = words[idx + 1].group(0) if idx + 1 < len(words) else ""
                if not _is_capitalised(prev_w) and not _is_capitalised(next_w):
                    hits.append((offset + m.start(), w))
        offset += len(sentence) + 1
    for _, tok in sorted(hits, key=lambda h: h[0]):
        if tok.lower() not in seen:
            seen.add(tok.lower()); found.append(tok)
    return found


def _norm_num(tok: str) -> str:
    return tok.replace(",", "").rstrip("%")


def _number_supported(tok: str, ctx_numbers: set[str]) -> bool:
    """Exact match, or a source figure that ROUNDS to the answer's figure at the answer's precision
    (sources say 79.14, the answer says 79.1): rounding is not invention."""
    a = _norm_num(tok)
    if a in ctx_numbers:
        return True
    try:
        decimals = len(a.split(".")[1]) if "." in a else 0
        target = round(float(a), decimals)
    except ValueError:
        return False
    for c in ctx_numbers:
        try:
            if "." in c and len(c.split(".")[1]) > decimals and round(float(c), decimals) == target:
                return True
        except ValueError:
            continue
    return False


def _word_supported(tok: str, ctx_lower: str) -> bool:
    # Case-insensitive, bounded by non-letters; a digit may touch it ("4GB" supports "GB").
    # Accept the singular/plural neighbour, removing ONE trailing "s" and never from "...ss"
    # (str.rstrip("s") would turn "faiss" into "fai" and "staleness" into "stalene").
    base = tok.lower()
    stem = base[:-1] if len(base) > 3 and base.endswith("s") and not base.endswith("ss") else base
    return re.search(r"(?<![a-z])" + re.escape(stem) + r"(?:s|es)?(?![a-z])", ctx_lower) is not None


def unsupported_specifics(answer: str, context: list[str]) -> list[str]:
    """Specifics in `answer` that no source mentions. Empty list = nothing checkable is unsupported."""
    ctx = "\n".join(context or [])
    ctx_lower = ctx.lower()
    ctx_numbers = {_norm_num(m.group(0).rstrip(".,")) for m in _NUMBER.finditer(ctx)}
    missing = []
    for tok in extract_specifics(answer):
        if tok[0].isdigit():
            if not _number_supported(tok, ctx_numbers):
                missing.append(tok)
        else:
            # "CNNs/RNNs": each side is judged on its own; the pair is supported if every part is.
            parts = [p for p in tok.split("/") if p] or [tok]
            if not all(_word_supported(p, ctx_lower) for p in parts):
                missing.append(tok)
    return missing
