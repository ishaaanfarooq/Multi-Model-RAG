"""The verifier evaluation's cases are built, not judged: their construction must be exact."""
import glob
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from eval.verifier_eval import (FABRICATION_ABSENT_TERMS, FABRICATIONS, VAGUE_FABRICATIONS, build_cases, format_table, insert_fabrication,
                                lexical_verdict, summarize, swap_number, trim_to_sentence)

CORPUS = " ".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(os.path.dirname(__file__), "..", "eval", "corpus", "*.txt"))).lower()


def test_every_fabrication_uses_a_term_the_corpus_never_uses():
    assert len(FABRICATIONS) == len(FABRICATION_ABSENT_TERMS)
    for sentence, term in zip(FABRICATIONS, FABRICATION_ABSENT_TERMS):
        assert term in sentence.lower()
        assert not re.search(r"\b" + re.escape(term), CORPUS), f"'{term}' occurs in the corpus: '{sentence}' is no longer a fabrication"


def test_fabrication_goes_after_the_first_sentence_not_at_the_end():
    out = insert_fabrication("FAISS is the vector store [1]. It is fast. It runs on CPU.", 0)
    assert out == "FAISS is the vector store [1]. " + FABRICATIONS[0] + " It is fast. It runs on CPU."
    assert insert_fabrication("One sentence only.", 1) == "One sentence only. " + FABRICATIONS[1]


def test_swap_number_changes_a_supported_figure_to_an_unsupported_one():
    ctx = "Chunks are 1000 characters with an overlap of 200. Top 10 candidates are reranked to 5."
    out = swap_number("The splitter uses 1000 characters and an overlap of 200 [1].", ctx)
    assert out == "The splitter uses 1350 characters and an overlap of 200 [1]."
    assert swap_number("It reranks to 5 [2].", ctx) is None, "single digits and citation markers are left alone"
    assert swap_number("The score was 0.78.", "recall was 0.78 overall") == "The score was 1.1."
    assert swap_number("It has 4096 tokens.", "no such number here") is None, "only figures the context supports are swapped"


def test_trim_to_sentence_drops_a_dangling_fragment():
    assert trim_to_sentence("First sentence. Second one is cut mid-wa") == "First sentence."
    assert trim_to_sentence("Complete. Also complete.") == "Complete. Also complete."
    assert trim_to_sentence("no terminator at all") == "no terminator at all"


def test_build_cases_makes_each_class_with_the_right_truth():
    base = [{"id": "q1", "source": "a.txt", "answer": "Chunks are 1000 characters [1]. Overlap is 200.", "context": ["Chunks are 1000 characters with overlap 200."], "gold_evidence": "1000 characters"},
            {"id": "q2", "source": "b.txt", "answer": "Ollama hosts the local model [1].", "context": ["Ollama hosts the local model on the GPU."], "gold_evidence": "Ollama hosts"}]
    cases = build_cases(base)
    by = {(c["id"], c["class"]): c for c in cases}
    assert by[("q1", "correct")]["answer"] == base[0]["answer"]
    assert FABRICATIONS[0] in by[("q1", "fabricated_sentence")]["answer"]
    assert VAGUE_FABRICATIONS[0] in by[("q1", "fabricated_vague")]["answer"]
    assert "1350" in by[("q1", "number_swapped")]["answer"] and ("q2", "number_swapped") not in by
    wd = by[("q1", "wrong_document")]
    assert wd["answer"] == base[1]["answer"] and wd["from"] == "q2" and wd["context"] == base[0]["context"]
    assert build_cases(base) == cases, "deterministic"


def test_wrong_document_is_skipped_when_every_other_answer_is_same_source_or_supported():
    base = [{"id": "q1", "source": "a.txt", "answer": "A.", "context": ["shared evidence text"], "gold_evidence": "shared evidence"},
            {"id": "q2", "source": "a.txt", "answer": "B.", "context": ["shared evidence text"], "gold_evidence": "shared evidence"}]
    assert not [c for c in build_cases(base) if c["class"] == "wrong_document"]


def test_summary_scores_each_class_against_its_own_truth():
    rows = [{"class": "correct", "support": 0.9, "lexical": True, "judge": True, "shipped": True},
            {"class": "correct", "support": 0.5, "lexical": None, "judge": True, "shipped": False},
            {"class": "fabricated_sentence", "support": 0.8, "lexical": True, "judge": True, "shipped": True},
            {"class": "fabricated_sentence", "support": 0.6, "lexical": None, "judge": False, "shipped": False}]
    s = summarize(rows, ("lexical", "judge", "shipped"))
    assert s["correct"]["shipped"] == {"pass": 1, "fail": 1, "undecided": 0, "correct_rate": 0.5}
    assert s["fabricated_sentence"]["lexical"] == {"pass": 1, "fail": 0, "undecided": 1, "correct_rate": 0.0}, "undecided is not a detection"
    assert s["fabricated_sentence"]["judge"]["correct_rate"] == 0.5
    assert lexical_verdict(0.75) is True and lexical_verdict(0.30) is False and lexical_verdict(0.5) is None
    table = format_table(s, ("lexical", "judge", "shipped"))
    assert "| fabricated_sentence | 2 | should FAIL | 0.70 |" in table and "1 undecided" in table


def test_vague_fabrications_really_contain_nothing_checkable():
    from verification.specifics import extract_specifics
    for sentence in VAGUE_FABRICATIONS:
        assert extract_specifics("FAISS is the store. " + sentence) == ["FAISS"], sentence
    for sentence in FABRICATIONS:
        assert extract_specifics(sentence), f"a specific fabrication must contain a specific: {sentence}"
