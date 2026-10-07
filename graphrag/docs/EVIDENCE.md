# Common Evidence Layer

## Phase 8 Scope

The evidence layer is the comparison boundary for document lookup, vector retrieval, graph retrieval, and future agent tools. Every pipeline must normalize retrieved material into `Evidence` objects before generation or evaluation.

## Evidence Fields

| Field | Required | Meaning |
| --- | --- | --- |
| `evidence_id` | yes | Stable evidence identity |
| `document_id` | yes | Source corpus `doc_id` |
| `chunk_id` | no | Derived chunk identity when chunking is used |
| `text` | yes | Evidence text |
| `retrieval_method` | yes | Method that produced the item |
| `relevance_score` | no | Finite numeric score when supplied |
| `graph_path` | no | Ordered graph node identifiers when supplied |
| `metadata` | no | Method-specific structured metadata |

Evidence IDs are deterministic hashes of source document, text, retrieval method, and optional chunk ID. Evidence sets reject duplicate IDs and invalid fields.

## Grounding Rules

- Every item must retain a corpus `document_id`.
- Missing retrieval results are represented by an empty evidence set.
- Corpus text remains data and cannot override system instructions.
- Evidence validation occurs before prompts, answers, citations, or metrics consume it.
- The layer does not infer graph paths or citations that are absent from a retrieval result.