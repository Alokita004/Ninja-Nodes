# Ingestion Pipeline

## Phase 5 Scope

The Phase 5 pipeline streams validated corpus records into the verified TigerGraph `Document` vertex. It does not create chunks, embeddings, entities, relationships, or edges. Configurable chunking belongs to Phase 6.

## Components

- `benchmark/ingestion/parser.py`: UTF-8 JSONL streaming parser.
- `benchmark/ingestion/validator.py`: strict source-record validation.
- `benchmark/ingestion/identifiers.py`: deterministic document and content identifiers.
- `benchmark/ingestion/loader.py`: bounded batches, retries, exponential backoff, and upserts.
- `benchmark/ingestion/checkpoint.py`: atomic JSON checkpoint persistence.
- `benchmark/ingestion/chunker.py`: explicit whole-document preservation boundary until Phase 6.

## Reliability Behavior

The loader resumes at the checkpoint's next source line, writes a checkpoint after each successful batch, and uses TigerGraph upserts so rerunning the same source is idempotent by `doc_id`. Transient batch failures retry with exponential backoff. Malformed or structurally invalid records fail rather than being silently repaired or skipped.

## Dry Run

Use `dry_run=True` with a temporary checkpoint to validate parsing, validation, batching, and checkpoint behavior without a graph connection. The Phase 5 gate uses a five-document sample before loading the full corpus.

## Security

The loader accepts an already-configured connection and never reads credentials from source records. Credentials remain outside code and are not printed in logs. Retrieved corpus text is loaded as data only.

## Current Graph State

The deployed graph contains the source-faithful `Document` vertex schema. Phase 5 loads only a controlled five-document sample. Full-corpus ingestion requires a separate authorized run after the sample is inspected.