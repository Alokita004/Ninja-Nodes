# Dataset Intelligence

Phase 0 was performed by streaming the repository-root JSONL files without modifying them.

## Located Inputs

| Dataset | Path | Records | Malformed records |
| --- | --- | ---: | ---: |
| Corpus | `./corpus.jsonl` | 2,951 | 0 |
| Public evaluation | `./eval_public.jsonl` | 100 | 0 |
| Hidden evaluation | `./eval_hidden.jsonl` | 50 | 0 |

## Corpus Observations

Every corpus record has the same seven non-null fields: `doc_id` (string), `title` (string), `url` (string), `wikidata_qid` (string), `wikipedia_pageid` (integer), `approx_tokens` (integer), and `text` (string). There are no duplicate `doc_id` values and no duplicate complete documents in the observed data.

Text length is 444 to 107,498 characters, with median 4,131. Whitespace-token length ranges from 62 to 17,577, with median 836. The records contain Olympic event articles and Wikipedia/Wikidata identifiers. No explicit top-level entity or relationship fields were observed; entity and relationship information is embedded in document text and infobox-like text, so it must not be treated as an established structured graph schema in this phase.

## Public Evaluation Observations

Every record has `qid`, `question`, `qtype`, `answer_named_in_question`, `guess_baseline`, `gold_doc_ids`, `answer_verified`, and `answer`. Types are string, string, string, boolean, number, array, boolean, and array respectively. No nulls or duplicate `qid` values were observed. Question length is 75 to 136 characters, with median 113. Every public record has a verified answer and gold document references; 547 references point to 518 unique corpus documents, and all referenced document IDs exist in the corpus.

The observed `qtype` values and public answers are recorded in the machine-readable profile. Public answers were inspected only for Phase 0 dataset characterization and were not used to tune any implementation.

## Hidden Evaluation Observations

Every hidden record exposes only `qid`, `question`, and `qtype`, all non-null. There are 50 records, no malformed records, and no duplicate `qid` values. Question length is 76 to 147 characters, with median 115. No answer, citation, or gold-document field is present in the observed hidden input. Hidden record values and any possible ground truth are intentionally excluded from generated artifacts and logs.

## Relationships Observed

The public `gold_doc_ids` field provides an explicit question-to-document evaluation relationship. No equivalent relationship field is exposed in the hidden data. The corpus has no explicit structured entity or relationship arrays; any derivation belongs to a later authorized phase.

## Reproducibility

Run the streaming profiler from the workspace root:

```text
python benchmark/dataset/profile.py --root . --output benchmark/dataset/profile.json
```

The profiler records field presence, observed types, nulls, malformed line numbers, duplicate counts, length distributions, public reference integrity, and question-type counts. Hidden values are redacted. No TigerGraph, embedding, ingestion, RAG, or agent operation is performed.