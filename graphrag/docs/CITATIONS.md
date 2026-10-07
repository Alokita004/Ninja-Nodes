# Citation Validation

## Phase 12 Scope

Citation validation checks the answer-to-evidence-to-document chain before an answer is considered grounded. It does not use hidden evaluation answers and does not infer support that is absent from the supplied evidence.

## Citation Format

Answers use document identifiers in square brackets, for example:

```text
The event was held in London [Q303623].
```

Each cited ID must exist in the supplied `EvidenceSet`. When corpus IDs are available, the cited ID must also resolve to the corpus.

## Metrics

- Citation precision: valid cited IDs divided by all cited IDs.
- Citation recall: cited evidence document IDs divided by all evidence document IDs.
- Evidence coverage: the same document-level coverage ratio.
- Unsupported claim rate: answer sentences without a citation divided by answer sentences.

Invalid or fabricated citations raise `CitationValidationError`; they are not silently removed.

## Limitations

The unsupported-claim metric is sentence-level citation coverage, not semantic entailment. Claim-level entailment requires a later evaluation/judge phase. Empty evidence and `INSUFFICIENT_EVIDENCE` answers remain valid only when no unsupported citation is present.