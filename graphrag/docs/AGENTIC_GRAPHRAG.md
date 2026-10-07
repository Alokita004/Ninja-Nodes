# Agentic GraphRAG

## Phase 11 Scope

The agentic pipeline uses LangGraph to coordinate approved deterministic retrieval tools, validate common evidence, record investigation traces, and stop within a configured step budget. It does not invent evidence or execute arbitrary graph queries.

## State

The controller tracks the question, observed question type, evidence, unresolved information, trace steps, tool calls, answer, citations, and stop reason. Hidden evaluation answers are not part of the state.

## Control Rules

- `aggregation`, `superlative`, and `temporal` questions prefer an approved `graph` tool when available.
- Other questions prefer the first approved tool.
- Evidence is deduplicated by `evidence_id`.
- Tool failures stop the investigation with `tool_failure`.
- Sufficient evidence goes to grounded synthesis.
- Empty evidence repeats until `max_steps`, then terminates without an unsupported answer.

## Trace

Each step records the agent, action, reason, tool, input/output summaries, evidence added, token count, and latency. Retrieved text is not copied into the trace summaries.

## Limitations

The current repository exposes only document-level vector and graph tools. Entity and relationship tools remain unavailable because the verified dataset and graph schema contain no explicit entity or relationship structures.