"""
Unsupported specifics: the concrete claims (figures, identifiers, names) an answer makes that its
sources never mention. Each false-alarm case below was a real one, found by reading outputs.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from verification.specifics import extract_specifics, unsupported_specifics

CTX = ["2.3 Vector Database: FAISS (Facebook AI Similarity Search). Chunks are 1,000 characters with an overlap of 200. "
       "Minimum: 16GB System RAM, 4GB VRAM. Traditional methods (like CNNs or RNNs) process text sequentially. "
       "This avoids hallucinations and information staleness. Sales reached 79.14 trillion won."]


def test_changed_figures_and_invented_identifiers_are_caught():
    assert unsupported_specifics("The splitter uses 1350 characters [1].", CTX) == ["1350"]
    assert unsupported_specifics("It was benchmarked on eight A100 GPUs and scored a BLEU of 41.2.", CTX) == ["A100", "BLEU", "41.2"]
    assert unsupported_specifics("User accounts live in a PostgreSQL 15 database.", CTX) == ["PostgreSQL", "15"]
    assert unsupported_specifics("Deployment is managed with Kubernetes across three zones.", CTX) == ["Kubernetes"]


def test_supported_specifics_pass_including_the_real_false_alarms():
    assert unsupported_specifics("FAISS stores the vectors; chunks are 1000 characters with overlap 200 [1].", CTX) == []   # 1,000 == 1000; "faiss" keeps both s's
    assert unsupported_specifics("The minimum RAM is **16GB** and VRAM is 4GB.", CTX) == []                                 # a unit glued to its digit
    assert unsupported_specifics("2. **Information Staleness:** the content may be out of date.", CTX) == []                # plural/-ness stemming; bold label
    assert unsupported_specifics("Unlike CNNs/RNNs it attends to the whole sequence.", CTX) == []                           # slash-joined pair
    assert unsupported_specifics("Revenue was 79.1 trillion won [2].", CTX) == [], "rounding a source figure is not invention"
    assert unsupported_specifics("Revenue was 79.4 trillion won [2].", CTX) == ["79.4"], "but a different figure is"


def test_prose_capitals_title_case_runs_citations_and_list_markers_are_not_specifics():
    assert extract_specifics("This happens in Large Language Models (LLMs).") == [], "a Title Case run, and LLMs is generic vocabulary"
    assert extract_specifics("such as Convolutional Neural Networks which read sequentially") == []
    assert extract_specifics("4. **Retrieval attacks** - Ineffective strategies might leak data.") == []
    assert extract_specifics("These errors are listed in Section 3.1 of the report [1], [Source 2].") == ["3.1"]
    assert extract_specifics("### Direct Answer\n1. First point.\n2. Second point.") == []
    assert extract_specifics("It has 3 tiers and 5 stages.") == [], "single digits are counts, too often written as words in the source"
    assert extract_specifics("However, Additionally, Therefore these hold.") == []


def test_extraction_is_ordered_deduplicated_and_tolerant_of_empty_input():
    assert extract_specifics("Each JWT expires after 30 minutes; every JWT is signed. Audio goes through Whisper first, then Whisper again.") == ["JWT", "30", "Whisper"]
    assert extract_specifics("Whisper transcribes the audio.") == [], "a sentence-initial capital proves nothing, so it is skipped"
    assert extract_specifics("") == [] and unsupported_specifics("", CTX) == [] and unsupported_specifics("A100 everywhere.", []) == ["A100"]


def test_generic_computing_vocabulary_is_wording_but_project_specific_acronyms_are_claims():
    """Both real false alarms: a FastAPI server 'serving HTTP' and an RTX card described as a 'GPU'."""
    assert unsupported_specifics("main.py starts the server and exposes the HTTP API; inference runs on the GPU.", CTX) == []
    assert unsupported_specifics("Every request carries a JWT and is served over TLS from AWS.", CTX) == ["JWT", "TLS", "AWS"]
