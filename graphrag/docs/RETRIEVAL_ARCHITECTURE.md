# Retrieval Architecture

## Purpose

Define comparable retrieval boundaries for Vector RAG, Hybrid GraphRAG, and Agentic GraphRAG using the verified public-question taxonomy. This document does not implement embeddings, graph queries, or RAG.

## Shared Retrieval Contract

Input:

```text
question: string
qid: string when available
qtype: observed dataset label
retrieval_budget: configured limit
```

Output candidates must preserve:

```text
document_id
text or derived chunk text
retrieval_method
relevance_score when available
metadata
graph_path when available
```

All candidates must be traceable to a corpus `doc_id`. Retrieval must return an explicit empty result when no evidence is found rather than fabricating context.

## Routing From Observed Taxonomy

| qtype | Primary retrieval need | Minimum architecture concern |
| --- | --- | --- |
| `lookup` | Identify one event document | Precise document matching |
| `multi_hop` | Resolve multiple clues within the event description | Preserve clues and source context |
| `temporal` | Resolve a relative Olympic edition and target event | Multi-document context and temporal interpretation |
| `aggregation` | Retrieve the candidate set before threshold counting | Recall and candidate completeness |
| `superlative` | Retrieve the candidate set before ranking | Recall and numeric attribute preservation |

These are retrieval requirements derived from public labels and reference breadth, not measured performance claims.

## Vector RAG Boundary

```text
Question
  -> question representation
  -> vector candidate retrieval
  -> evidence normalization
  -> grounded generation
```

Vector RAG must use the same corpus and answer requirements as the other modes. It must report top-k, scores, retrieval latency, generation latency, token counts, and citations. For aggregation and superlative questions, a single top-k result must not be described as complete candidate coverage without measurement.

## Hybrid GraphRAG Boundary

```text
Question
  -> deterministic taxonomy routing
  -> vector candidates
  -> graph candidates when a verified graph operation exists
  -> deduplication and evidence merge
  -> grounded generation
```

The graph branch is conditional. Since no explicit entities or relationships were found in the corpus, Phase 3 does not prescribe graph queries. A later graph phase must prove that a graph operation is supported before routing questions to it.

## Agentic GraphRAG Boundary

```text
Question
  -> bounded planner
  -> deterministic retrieval tool
  -> evidence sufficiency check
  -> bounded follow-up or synthesis
```

The agent may choose among approved tools, but it cannot invent evidence, execute arbitrary graph language, or use hidden evaluation answers. Every action must record its reason, tool, input summary, output summary, evidence gained, latency, and token usage.

## Fairness Requirements

- Same corpus and public question set.
- Same configured generation model and answer instructions.
- Same citation and evidence validation rules.
- Pipeline-specific retrieval is allowed only when its available information is documented.
- Retrieval results must be normalized before comparing quality or efficiency.
- Public gold references may be used for evaluation, never for answer-time retrieval.