# GraphMind Final Submission Package

## Problem
This benchmark system compares three retrieval strategies on a fixed corpus and public evaluation set:

- Vector RAG
- Hybrid GraphRAG
- Agentic GraphRAG

The objective is to answer questions using only the supplied corpus and to evaluate answer quality, grounding, citation validity, latency, token efficiency, and agentic investigation behavior.

## Dataset
The system uses the authoritative corpus and evaluation files in the workspace root:

- corpus.jsonl
- eval_public.jsonl
- eval_hidden.jsonl

The dataset contract was validated before benchmark execution. Hidden evaluation records were not used for tuning, prompting, or answer fabrication.

## Architecture
The benchmark follows a common evidence boundary across all pipelines:

- Vector RAG retrieves candidate document evidence and grounds generation from that evidence.
- Hybrid GraphRAG merges vector retrieval with document-level graph retrieval and normalizes results to the same evidence schema.
- Agentic GraphRAG performs bounded investigation using deterministic tools and records trace steps, tool choices, evidence gained, and stop reason.

The common contract ensures all pipelines produce comparable output records, citations, tokens, and latency.

## TigerGraph Usage
TigerGraph is treated as the verified graph retrieval backend when available. The benchmark design keeps graph access deterministic and constrained to the verified dataset-supported surface. No hidden answer data is used in graph retrieval or generation.

## Agent Design
The agentic controller is bounded and deterministic:

- plan the next retrieval action
- call an approved tool
- evaluate whether evidence is sufficient
- synthesize only from supplied evidence
- stop on evidence sufficiency, max-step termination, or tool failure

Every trace step records the agent, action, tool, reason, evidence gained, tokens, and latency.

## Evidence and Citation System
Every pipeline normalizes outputs to a common evidence object and then validates citation support before accepting an answer as grounded. Unsupported or missing evidence leads to insufficient-evidence handling instead of invented citations.

## Evaluation Methodology
The benchmark compares pipeline outputs on the same public questions and uses a deterministic judge for public answer matching. Results are normalized into benchmark records and aggregated into summary metrics including:

- correctness
- evidence count
- total tokens
- latency
- failure rate
- pipeline comparison

Public evaluation is used only for benchmark measurement. Hidden evaluation results are kept sealed and submitted only as output records without hidden answer leakage.

## Metrics
The final benchmark output includes:

- per-pipeline record files
- aggregate metrics
- comparison summary
- hidden submission bundle

## Reproduction
Run the benchmark suite from the project root:

```bash
cd graphrag
python -m pytest benchmark/tests -q
```

The frozen config is stored in:

- FINAL_BENCHMARK_CONFIG.yaml

The generated benchmark outputs are stored in:

- results/public/
- results/hidden/
- FINAL_RESULTS/

## Security
- No credentials, API keys, or TigerGraph secrets are stored in repository files.
- Hidden answers are not exposed in logs, prompts, output files, or benchmark reports.
- Retrieval content is treated as data, not instructions.

## Limitations
This final package is a benchmark-ready, verified scaffolding and dataset-grounded output bundle. It is not a live production benchmark against external LLM providers or a live TigerGraph deployment unless those services are configured in the environment.
