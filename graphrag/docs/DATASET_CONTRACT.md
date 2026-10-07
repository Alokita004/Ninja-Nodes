# Dataset Contract

This contract is derived only from the Phase 0 inspection of `corpus.jsonl`, `eval_public.jsonl`, and `eval_hidden.jsonl`. It describes the observed JSONL records and does not define a TigerGraph schema, embeddings, chunking, retrieval, or agents.

## Document

Every corpus record contains these required, non-null fields:

| Field | Type | Meaning |
| --- | --- | --- |
| `doc_id` | string | Corpus document identifier |
| `title` | string | Document title |
| `url` | string | Source URL |
| `wikidata_qid` | string | Wikidata identifier |
| `wikipedia_pageid` | integer | Wikipedia page identifier |
| `approx_tokens` | integer | Dataset-provided approximate token count |
| `text` | string | Document text |

The observed corpus contains 2,951 records, with no duplicate identifiers or complete duplicate records. The metadata concept is represented by the confirmed flat fields `title`, `url`, `wikidata_qid`, `wikipedia_pageid`, and `approx_tokens`; no separate metadata object exists in the input.

## Question

The common question fields observed in both evaluation files are:

| Field | Type | Meaning |
| --- | --- | --- |
| `qid` | string | Question identifier |
| `question` | string | Question text |
| `qtype` | string | Dataset-provided question type label |

The hidden evaluation file contains only these three fields. It has no answer, citation, or gold-document field.

## Answer

In public evaluation records, `answer` is a required non-null array of strings. The observed public dataset has this field in all 100 records. The validator does not interpret answer semantics or alter answer values.

## Citation

No standalone `citation` field is present. Public evaluation records expose `gold_doc_ids`, a required non-null array of strings. Each value is a document identifier and is treated as a document citation/reference for contract validation. Every observed public reference resolves to a `doc_id` in the corpus.

## Metadata

No standalone metadata object or metadata field is present. The confirmed document metadata fields are the five flat fields listed in the Document section. No unobserved metadata fields are added to this contract.

## Public Evaluation Record

Every public record contains these required, non-null fields:

| Field | Type |
| --- | --- |
| `qid` | string |
| `question` | string |
| `qtype` | string |
| `answer_named_in_question` | boolean |
| `guess_baseline` | number |
| `gold_doc_ids` | array of strings |
| `answer_verified` | boolean |
| `answer` | array of strings |

The observed public evaluation contains 100 records and no duplicate `qid` values.

## Hidden Evaluation Record

Every hidden record contains exactly `qid`, `question`, and `qtype`, all as non-null strings. The validator rejects extra fields, including any answer or gold-document field, so hidden ground truth cannot enter the contract accidentally.

## Validation Behavior

`benchmark/dataset/validator.py` streams each file and fails with `DatasetValidationError` if it encounters malformed JSON, a non-object record, unknown or missing fields, nulls, invalid types, duplicate IDs, duplicate complete corpus documents, or public references to unknown corpus documents. It never repairs or silently skips invalid input.