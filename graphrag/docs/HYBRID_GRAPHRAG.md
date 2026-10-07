# Hybrid GraphRAG

## Phase 10 Scope

Hybrid GraphRAG merges vector retrieval with the verified document-level TigerGraph query surface. It uses the observed question taxonomy to request broader graph candidate sets for `aggregation`, `superlative`, and `temporal` questions. It does not claim entity traversal because no entity or relationship schema exists.

## Flow

```text
Question + qtype
  -> vector top-k retrieval
  -> document graph candidate retrieval
  -> deterministic evidence merge by document_id
  -> grounded generation
  -> answer, citations, and metrics
```

## Metrics

The pipeline records vector result count, graph result count, merged evidence count, graph query count, token counts, retrieval latency, generation latency, and total latency.

## Fairness

The pipeline shares the Vector RAG model, generator, corpus, evidence validation, citation representation, and grounded prompt requirements. Graph-specific evidence is explicitly labeled `graph_document`.

## Limitations

The graph branch currently retrieves bounded `Document` vertices only. No graph traversal, entity lookup, relationship reasoning, or live LLM/embedding call was added in Phase 10.