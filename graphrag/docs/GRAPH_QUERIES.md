# Graph Query Layer

## Phase 7 Scope

The deployed graph currently exposes only the source-faithful `Document` vertex. Phase 7 therefore implements only document count, exact document lookup, and bounded document listing. Entity lookup, relationship traversal, multi-hop traversal, temporal traversal, and graph aggregation are not implemented because their schemas are not present.

## Operations

| Operation | Input | Output | Timeout/error behavior |
| --- | --- | --- | --- |
| `document_count` | none | `DocumentCount` | Read-only count; wraps backend failures as `GraphQueryError` |
| `document_by_id` | non-empty `document_id` | `DocumentRecord` or `None` | Exact ID lookup; invalid IDs fail locally |
| `list_documents` | `limit` from 1 to 1000 | bounded raw rows | Backend timeout configured; invalid bounds fail locally |

All operations use pyTigerGraph APIs rather than dynamic GSQL. Document IDs and source attributes remain traceable to the corpus contract.

## Verification

Each query has a fake-connection fixture for deterministic unit testing. Live graph connectivity and schema checks were completed in Phase 4. Live query execution against the five-document sample is intentionally limited to read-only verification; no new data is written in Phase 7.