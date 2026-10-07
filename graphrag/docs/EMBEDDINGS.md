# Chunking and Embedding Engine

## Phase 6 Scope

Phase 6 adds deterministic document chunking, configurable embedding orchestration, persistent caching, retry behavior, and vector validation. It does not load embeddings into TigerGraph or run a full-corpus embedding job.

## Configuration

The embedding model is read from the configured `llm_config.embedding_service.model_name`. Optional engine settings are:

```text
batch_size
max_retries
backoff_seconds
dimensions
```

`dimensions` is optional. When absent, the engine infers the dimension from returned vectors and rejects inconsistent batches. The engine does not assume a provider-specific dimension.

## Chunking

`chunk_document` uses configurable character size and overlap. Every chunk has a deterministic ID derived from the document ID, ordinal, and chunk text. Phase 5 ingestion intentionally preserved whole documents; Phase 6 chunking is a separate derived operation and has not been written into the graph.

## Cache

The SQLite cache identity is:

```text
sha256(content) + model_name
```

Cached vectors are validated before use. Changing either content or model name produces a distinct cache entry.

## Reliability

Embedding batches retry with exponential backoff. The engine validates vector count, numeric values, non-empty vectors, configured dimensions when supplied, and consistent dimensions across a result.

## Verification

Local tests verify deterministic chunks, cache hits, retry behavior, inferred dimensions, and invalid configuration. Provider API availability has not been claimed or tested; a live provider check requires an explicit controlled call using the configured external service.