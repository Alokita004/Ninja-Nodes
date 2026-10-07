"""Bounded LangGraph investigation controller."""

from __future__ import annotations

import time
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Callable, Protocol

from langgraph.graph import END, START, StateGraph

from benchmark.evidence.models import Evidence, EvidenceSet
from benchmark.evidence.validator import validate_evidence_set

from .models import InvestigationState, TraceStep


class InvestigationTool(Protocol):
    name: str

    def run(self, question: str, question_type: str) -> EvidenceSet:
        ...


class SynthesisModel(Protocol):
    def generate(self, prompt: str) -> str:
        ...


@dataclass(frozen=True)
class InvestigationResult:
    answer: str
    evidence: tuple[Evidence, ...]
    citations: tuple[str, ...]
    steps: tuple[TraceStep, ...]
    tool_calls: tuple[str, ...]
    stop_reason: str


class AgenticGraphRAG:
    def __init__(self, tools: list[InvestigationTool], synthesizer: SynthesisModel, *, max_steps: int = 3, sufficient_evidence: int = 1):
        if not tools:
            raise ValueError("at least one investigation tool is required")
        if max_steps < 1 or sufficient_evidence < 1:
            raise ValueError("max_steps and sufficient_evidence must be positive")
        self.tools = {tool.name: tool for tool in tools}
        self.synthesizer = synthesizer
        self.max_steps = max_steps
        self.sufficient_evidence = sufficient_evidence
        self.graph = self._build_graph()

    def investigate(self, question: str, question_type: str) -> InvestigationResult:
        result = self.graph.invoke(self._initial_state(question, question_type))
        return self._result(result)

    def stream(self, question: str, question_type: str) -> Iterator[tuple[str, TraceStep | InvestigationResult]]:
        emitted_steps = 0
        final_state: InvestigationState | None = None
        for state in self.graph.stream(self._initial_state(question, question_type), stream_mode="values"):
            steps = state["steps"]
            for step in steps[emitted_steps:]:
                yield "step", step
            emitted_steps = len(steps)
            final_state = state
        if final_state is None:
            raise RuntimeError("investigation produced no state")
        yield "result", self._result(final_state)

    @staticmethod
    def _initial_state(question: str, question_type: str) -> InvestigationState:
        return {
            "question": question,
            "question_type": question_type,
            "evidence": [],
            "unresolved_information": [question],
            "steps": [],
            "tool_calls": [],
            "answer": "",
            "citations": [],
            "stop_reason": "",
            "current_tool": "",
        }

    @staticmethod
    def _result(state: InvestigationState) -> InvestigationResult:
        return InvestigationResult(
            state["answer"],
            tuple(state["evidence"]),
            tuple(state["citations"]),
            tuple(state["steps"]),
            tuple(state["tool_calls"]),
            state["stop_reason"],
        )

    def _build_graph(self):
        graph = StateGraph(InvestigationState)
        graph.add_node("plan", self._plan)
        graph.add_node("tool", self._tool)
        graph.add_node("evaluate", self._evaluate)
        graph.add_node("synthesize", self._synthesize)
        graph.add_edge(START, "plan")
        graph.add_edge("plan", "tool")
        graph.add_edge("tool", "evaluate")
        graph.add_conditional_edges("evaluate", self._next, {"plan": "plan", "synthesize": "synthesize", "finish": END})
        graph.add_edge("synthesize", END)
        return graph.compile()

    def _plan(self, state: InvestigationState) -> dict:
        # Deterministic planner: prefer broader tools for set questions, then
        # fall back to the first approved tool for follow-up investigation.
        preferred = "graph" if state["question_type"] in {"aggregation", "superlative", "temporal"} and "graph" in self.tools else next(iter(self.tools))
        return {"current_tool": preferred}

    def _tool(self, state: InvestigationState) -> dict:
        tool_name = state["current_tool"]
        tool = self.tools[tool_name]
        started = time.perf_counter()
        try:
            found = tool.run(state["question"], state["question_type"])
            validate_evidence_set(found)
            existing = {item.evidence_id for item in state["evidence"]}
            added = [item for item in found.items if item.evidence_id not in existing]
            step = TraceStep(len(state["steps"]) + 1, "investigator", "tool_call", "collect approved evidence", tool_name, "question and type", f"{len(added)} evidence items", len(added), 0, time.perf_counter() - started)
            return {"evidence": state["evidence"] + added, "steps": state["steps"] + [step], "tool_calls": state["tool_calls"] + [tool_name]}
        except Exception as error:
            step = TraceStep(len(state["steps"]) + 1, "investigator", "tool_failure", "approved tool failed", tool_name, "question and type", type(error).__name__, 0, 0, time.perf_counter() - started)
            return {"steps": state["steps"] + [step], "tool_calls": state["tool_calls"] + [tool_name], "stop_reason": "tool_failure"}

    def _evaluate(self, state: InvestigationState) -> dict:
        if state["stop_reason"]:
            return {}
        if len(state["evidence"]) >= self.sufficient_evidence:
            return {"stop_reason": "evidence_sufficient", "unresolved_information": []}
        return {"unresolved_information": [state["question"]]}

    def _next(self, state: InvestigationState) -> str:
        if state["stop_reason"] == "tool_failure":
            return "finish"
        if len(state["evidence"]) >= self.sufficient_evidence:
            return "synthesize"
        if len(state["steps"]) >= self.max_steps:
            return "finish"
        return "plan"

    def _synthesize(self, state: InvestigationState) -> dict:
        context = "\n\n".join(f"[{item.document_id}] {item.text}" for item in state["evidence"])
        prompt = "Use only supplied evidence. Do not use external knowledge.\nQuestion: " + state["question"] + "\nEvidence:\n" + context
        answer = self.synthesizer.generate(prompt)
        return {"answer": answer, "citations": [item.document_id for item in state["evidence"]], "stop_reason": "synthesized"}