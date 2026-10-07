# Common Benchmark Framework

## Phase 13 Scope

The benchmark framework normalizes Vector RAG, Hybrid GraphRAG, and Agentic GraphRAG outputs into `BenchmarkRecord` objects. It runs the public evaluation stream only, applies a deterministic answer judge, aggregates efficiency/retrieval metrics, and writes JSON reports.

## Fairness Contract

Each pipeline is evaluated on the same public questions, corpus, answer expectations, citation representation, and metrics. Pipeline-specific retrieval is allowed, but outputs are normalized before comparison.

As pipeline result files are added, the comparison writer checks that their ordered question IDs and serialized benchmark configurations match. A mismatch raises an error instead of presenting the runs as comparable. The reports include per-pipeline metric summaries; creating these reports does not itself execute a benchmark.

## Metrics

The framework records exact-match correctness, expected-answer coverage, retrieval Precision@K/Recall@K/MRR from public `gold_doc_ids`, citation-to-evidence precision and recall, evidence coverage, a citation-based grounding proxy, token totals, total/retrieval/generation latency, evidence count, empty-retrieval and failure/timeout rates, and agent steps/tool calls/strategy changes/stop reason. Each per-question record also carries retrieval methods and its individual measurements.

Completeness is the fraction of expected answer strings present in the normalized response. Grounding is a citation-to-retrieved-evidence validity proxy; it is not semantic entailment. The framework does not claim semantic completeness or claim-level entailment without a separately configured judge.

## Security

The runner reads only public evaluation records. It does not open `eval_hidden.jsonl`, write hidden answers, or send records to external services. Pipeline errors are recorded as typed failure records rather than silently omitted.

## Limitations

This phase provides the common runner and deterministic judge. LLM-based semantic judging and full public benchmark execution against live providers require a later configured evaluation run. No benchmark results are claimed merely from unit tests.