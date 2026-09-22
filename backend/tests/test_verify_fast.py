"""Verification tries the model-free proxy first and consults the model only when unsure."""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.text_support import count_numbers, lexical_support
from verification.verifier import VerificationModule

CTX = ["FAISS is the vector database. Ollama hosts the local model. The reranker is a cross-encoder."]


def _module(monkeypatch, llm_reply="Result: PASS\nReason: fine"):
    v = VerificationModule.__new__(VerificationModule)
    calls = []
    class LLM:
        def invoke(self, prompt, model_choice="auto"):
            calls.append(prompt); return llm_reply
    v.llm = LLM()
    from langchain_core.prompts import PromptTemplate
    v.prompt_template = PromptTemplate(input_variables=["context", "answer"], template="{context}\n{answer}")
    return v, calls


def test_grounded_answer_passes_without_a_model_call(monkeypatch):
    v, calls = _module(monkeypatch)
    ok, reason = asyncio.run(v.verify_fast("FAISS is the vector database. Ollama hosts the local model.", CTX))
    assert ok and calls == [] and "lexical support" in reason


def test_invented_answer_fails_without_a_model_call(monkeypatch):
    v, calls = _module(monkeypatch)
    ok, reason = asyncio.run(v.verify_fast("The system was deployed to Kubernetes on Azure last spring by a team of twelve.", CTX))
    assert not ok and calls == []


def test_uncertain_answer_consults_the_model_with_trimmed_context(monkeypatch):
    v, calls = _module(monkeypatch, "Result: FAIL\nReason: numbers invented")
    mixed = "FAISS is the vector database. It was rolled out to every regional office last spring."   # 0.5 support, no checkable specifics
    big_ctx = ["x" * 5000] * 6
    ok, reason = asyncio.run(v.verify_fast(mixed, CTX + big_ctx))
    assert calls, "model consulted in the uncertain band"
    assert len(calls[0]) < 3 * 1500 + 2000, "context trimmed to the first chunks"
    assert not ok and "model consulted" in reason


def test_count_numbers():
    assert count_numbers("Jan 100, Feb 75, Mar 50") == 3
    assert count_numbers("no numbers here") == 0
    assert count_numbers("revenue rose 12.5% to $93.8 trillion in Q4") == 2


def test_a_changed_figure_in_a_fully_supported_answer_fails_without_a_model_call(monkeypatch):
    """The gap the verifier evaluation found: support 1.0, so it used to auto-pass."""
    v, calls = _module(monkeypatch)
    ctx = ["The splitter produces chunks of 1000 characters with an overlap of 200 characters."]
    ok, reason = asyncio.run(v.verify_fast("The splitter produces chunks of 1350 characters with an overlap of 200 characters.", ctx))
    assert not ok and calls == [] and "'1350'" in reason
    ok, _ = asyncio.run(v.verify_fast("The splitter produces chunks of 1000 characters with an overlap of 200 characters.", ctx))
    assert ok and calls == []


def test_an_invented_sentence_with_specifics_fails_before_the_model_is_asked(monkeypatch):
    v, calls = _module(monkeypatch, "Result: PASS\nReason: looks fine")          # the lenient judge would have passed it
    ok, reason = asyncio.run(v.verify_fast("FAISS is the vector database. It was deployed to Kubernetes on Azure last spring.", CTX))
    assert not ok and calls == [] and "Kubernetes" in reason and "Azure" in reason


def test_specifics_check_can_be_switched_off(monkeypatch):
    v, calls = _module(monkeypatch)
    v.CHECK_SPECIFICS = False
    ctx = ["The splitter produces chunks of 1000 characters with an overlap of 200 characters."]
    ok, _ = asyncio.run(v.verify_fast("The splitter produces chunks of 1350 characters with an overlap of 200 characters.", ctx))
    assert ok, "old behaviour: lexical support alone"


def test_warning_names_the_specifics_and_otherwise_keeps_the_branch_wording():
    from verification.verifier import GENERIC_WARNING, unsupported_specifics_reason, warning_for
    reason = unsupported_specifics_reason(["41.2", "A100"])
    assert warning_for(reason) == "Check before relying on this: the answer mentions '41.2', 'A100', which do not appear in the retrieved sources."
    assert warning_for("The judge said no.") == GENERIC_WARNING
    assert warning_for("The judge said no.", fallback="Treat figures as approximate.") == "Treat figures as approximate."
    assert "(and 2 more)" in unsupported_specifics_reason(list("abcdefg"))
