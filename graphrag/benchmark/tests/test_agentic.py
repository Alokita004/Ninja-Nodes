from __future__ import annotations

from benchmark.agents.controller import AgenticGraphRAG
from benchmark.agents.models import TraceStep
from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import evidence_id


def evidence(document_id: str) -> Evidence:
    text = "supported text"
    return Evidence(evidence_id(document_id, text, "fake"), document_id, text, "fake")


class Tool:
    def __init__(self, name, items):
        self.name = name
        self.items = items
        self.calls = 0

    def run(self, question, question_type):
        self.calls += 1
        return EvidenceSet.from_items(self.items)


class FailingTool(Tool):
    def run(self, question, question_type):
        self.calls += 1
        raise RuntimeError("failed")


class Synthesizer:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt):
        self.calls += 1
        return "grounded answer"


def test_one_step_investigation_synthesizes() -> None:
    tool = Tool("vector", [evidence("d1")])
    result = AgenticGraphRAG([tool], Synthesizer(), max_steps=3).investigate("question", "lookup")
    assert result.answer == "grounded answer"
    assert result.stop_reason == "synthesized"
    assert result.citations == ("d1",)
    assert len(result.steps) == 1


def test_investigation_stream_emits_step_before_synthesis() -> None:
    synthesizer = Synthesizer()
    agent = AgenticGraphRAG([Tool("vector", [evidence("d1")])], synthesizer)
    events = agent.stream("question", "lookup")

    event, step = next(events)
    assert event == "step"
    assert step.step_id == 1
    assert synthesizer.calls == 0

    event, result = next(events)
    assert event == "result"
    assert result.answer == "grounded answer"
    assert synthesizer.calls == 1


def test_multi_step_investigation_stops_at_budget() -> None:
    tool = Tool("vector", [])
    result = AgenticGraphRAG([tool], Synthesizer(), max_steps=2).investigate("question", "lookup")
    assert result.answer == ""
    assert result.stop_reason == ""
    assert len(result.steps) == 2


def test_tool_failure_stops_investigation() -> None:
    result = AgenticGraphRAG([FailingTool("vector", [])], Synthesizer()).investigate("question", "lookup")
    assert result.stop_reason == "tool_failure"
    assert result.answer == ""


def test_question_type_selects_graph_tool() -> None:
    graph = Tool("graph", [evidence("g1")])
    vector = Tool("vector", [evidence("v1")])
    result = AgenticGraphRAG([vector, graph], Synthesizer()).investigate("question", "aggregation")
    assert graph.calls == 1
    assert vector.calls == 0
    assert result.answer == "grounded answer"