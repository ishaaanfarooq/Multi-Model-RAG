"""
Tests for the deterministic chart path.

The bug these guard against: a small local model (Qwen 3B) cannot reliably WRITE
matplotlib — it hallucinated placeholder data ("Category 1/2/3") and buggy code, so a
"make a chart of my data" request produced a chart of fabricated numbers (or none). The
fix splits the job: the LLM only EXTRACTS the data as JSON, and we render it with a fixed,
correct template. These tests pin both halves.

Run:  cd backend && source venv/bin/activate && python -m pytest tests/test_visualizer.py -v
"""

import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from retrieval.visualizer import VisualizerAgent


class FakeLLM:
    def __init__(self, response: str):
        self.response = response

    def invoke(self, prompt: str, model_choice: str = "auto") -> str:
        return self.response


@pytest.fixture
def viz():
    d = tempfile.mkdtemp(prefix="praxis_viz_")
    agent = VisualizerAgent(output_dir=d)
    return agent


# ── extraction (the only LLM step) ────────────────────────────────────────────

def test_extract_parses_points_title_and_kind(viz):
    viz.llm = FakeLLM('{"title": "Sales", "kind": "line", '
                      '"points": [{"label": "Jan", "value": 100}, {"label": "Feb", "value": 75}]}')
    data = viz.extract_data_points("chart jan 100 feb 75")
    assert data["title"] == "Sales"
    assert data["kind"] == "line"
    assert data["points"] == [("Jan", 100.0), ("Feb", 75.0)]


def test_extract_tolerates_code_fences_and_prose(viz):
    viz.llm = FakeLLM('Sure! ```json\n{"kind":"bar","points":[{"label":"A","value":3}]}\n``` done')
    data = viz.extract_data_points("chart A 3")
    assert data["points"] == [("A", 3.0)]
    assert data["kind"] == "bar"


def test_extract_raises_when_no_numbers(viz):
    viz.llm = FakeLLM('{"title": "x", "kind": "bar", "points": []}')
    with pytest.raises(ValueError):
        viz.extract_data_points("make me a chart")


def test_extract_defaults_unknown_kind_to_bar(viz):
    viz.llm = FakeLLM('{"kind": "sankey", "points": [{"label": "A", "value": 1}, {"label": "B", "value": 2}]}')
    assert viz.extract_data_points("q")["kind"] == "bar"


def test_extract_pie_with_negative_falls_back_to_bar(viz):
    # A pie can't render negative slices; the extractor downgrades it to a bar chart.
    viz.llm = FakeLLM('{"kind": "pie", "points": [{"label": "A", "value": 5}, {"label": "B", "value": -3}]}')
    assert viz.extract_data_points("q")["kind"] == "bar"


# ── deterministic render (no LLM) — real numbers, real PNG, never a code crash ─

@pytest.mark.parametrize("kind", ["bar", "line", "pie"])
def test_render_writes_a_real_png(viz, kind):
    points = [("Jan", 100.0), ("Feb", 75.0), ("Mar", 50.0)]
    filename = viz.render_data_chart(points, title="Test", kind=kind)
    path = os.path.join(viz.output_dir, filename)
    assert os.path.isfile(path)
    with open(path, "rb") as f:
        assert f.read(8) == b"\x89PNG\r\n\x1a\n"  # PNG magic — it's a valid image


def test_render_handles_many_points(viz):
    points = [(m, float(v)) for m, v in zip(
        ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"],
        range(120, 0, -10))]
    filename = viz.render_data_chart(points, title="Year", kind="line")
    assert os.path.isfile(os.path.join(viz.output_dir, filename))
