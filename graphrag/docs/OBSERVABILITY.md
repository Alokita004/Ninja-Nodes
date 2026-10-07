# Phase 18 — Observability and Reproducibility

This benchmark keeps a reproducible configuration snapshot for every run.

## Configuration contract

Each run records:

- LLM model
- embedding model
- configuration version
- chunk size
- chunk overlap
- top K
- temperature
- max agent steps
- context limit
- judge method

The configuration is converted to a canonical JSON payload and a SHA-256-based configuration identifier is generated from that payload. The identifier is deterministic for identical settings.

`BenchmarkConfig.load()` reads `FINAL_BENCHMARK_CONFIG.yaml`. The version and judge method are part of the canonical JSON payload, so changing either changes the SHA-256-based configuration identifier. Identical settings produce the same identifier.

## Run metadata

Every benchmark execution emits a run record with:

- run_id
- timestamp
- configuration_id
- configuration_version
- pipeline
- question_id

This metadata is included in the API response for each query and can be attached to benchmark results, logs, and downstream evaluations.

## Structured logging

The observability helper emits structured logging records with run metadata and allowlisted counters/status fields. Question text, document text, prompts, credentials, and arbitrary exception messages are excluded.

## Repeatability requirement

The same benchmark configuration and same question set must produce the same configuration identifier for fair comparison across pipelines.
