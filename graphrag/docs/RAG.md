# Vector RAG Baseline

## Phase 9 Scope

The Vector RAG baseline embeds source documents and a question, ranks documents by cosine similarity, normalizes the selected results into the common evidence layer, and sends a grounded prompt to a configured answer generator. It does not use graph traversal.

## Flow

```text
Question
  -> question embedding
  -> cosine ranking
  -> top-k evidence
  -> grounded prompt
  -> answer + citations + metrics
```

The generator receives the explicit instructions to use only supplied evidence, avoid external knowledge, and report insufficient evidence. Empty retrieval returns `INSUFFICIENT_EVIDENCE` without calling the generator.

## Metrics

The baseline records input, output, and total whitespace-token counts; retrieval, generation, and total latency; and retrieved evidence count. These are operational metrics, not quality scores.

## Limitations

The implementation uses an in-memory document vector index and a provider-neutral model/generator protocol. A production run must supply the configured embedding provider and LLM, verify dimensions and API availability, and persist/index the full corpus. No live LLM or embedding call was made in Phase 9 tests.