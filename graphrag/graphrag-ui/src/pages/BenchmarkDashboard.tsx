import { FormEvent, useEffect, useRef, useState } from "react";
import { Activity, ArrowLeft, Check, CircleAlert, Clock3, FileText, GitBranch, LoaderCircle, Play, RefreshCw, Rows3, Square, Zap } from "lucide-react";
import { Link } from "react-router-dom";
import "./BenchmarkDashboard.css";

type PipelineId = "rag" | "graphrag" | "agentic";

type EvidenceItem = {
  evidence_id?: string;
  document_id?: string;
  chunk_id?: string | null;
  text?: string;
  retrieval_method?: string;
  relevance_score?: number | null;
  graph_path?: string[] | null;
};

type TraceStep = {
  step_id: number;
  agent?: string;
  action?: string;
  reason?: string;
  tool?: string;
  input_summary?: string;
  output_summary?: string;
  evidence_added?: number;
  tokens?: number;
  latency_seconds?: number;
};

type QueryResult = {
  answer: string;
  citations: string[];
  evidence: EvidenceItem[];
  pipeline: PipelineId;
  tokens: number;
  latency: number;
  metrics: Record<string, number>;
  steps: number;
  trace: TraceStep[];
  stop_reason: string | null;
  errors: string[];
  run_id: string;
};

type QueryState = {
  status: "running" | "complete" | "failed" | "cancelled";
  result?: QueryResult;
  trace: TraceStep[];
  error?: string;
};

type BenchmarkRecord = {
  correct?: boolean | null;
  grounding?: number | null;
  citation_precision?: number | null;
  citation_recall?: number | null;
  agent_steps?: number;
  total_tokens?: number;
  latency_seconds?: number;
  error?: string | null;
};

type PipelineResult = {
  record_count?: number;
  config?: { llm_model?: string };
  records?: BenchmarkRecord[];
};

type PipelineDefinition = {
  id: PipelineId;
  name: string;
  file: string;
  accent: string;
  description: string;
};

const pipelineDefinitions: PipelineDefinition[] = [
  { id: "rag", name: "Vector RAG", file: "rag_results.json", accent: "coral", description: "Vector retrieval baseline" },
  { id: "graphrag", name: "GraphRAG", file: "graphrag_results.json", accent: "mint", description: "Hybrid graph + vector retrieval" },
  { id: "agentic", name: "Agentic GraphRAG", file: "agentic_results.json", accent: "sky", description: "Bounded, tool-driven investigation" },
];

const questionTypes = ["lookup", "multi_hop", "temporal", "aggregation", "superlative"] as const;

type ApiHealth = {
  ready: boolean;
  configured_pipelines: string[];
};

async function getApiError(response: Response): Promise<string> {
  try {
    const body = await response.json() as { detail?: string | { code?: string } };
    if (typeof body.detail === "string") return body.detail;
    if (body.detail?.code) return body.detail.code.split("_").join(" ");
  } catch {
    // Use the HTTP status when the backend didn't return JSON.
  }
  return `Request failed (${response.status})`;
}

async function queryPipeline(
  pipeline: PipelineId,
  question: string,
  qtype: string | undefined,
  signal: AbortSignal,
): Promise<QueryResult> {
  const response = await fetch(`/api/query/${pipeline}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, qtype }),
    signal,
  });
  if (!response.ok) throw new Error(await getApiError(response));
  return await response.json() as QueryResult;
}

async function streamAgentic(
  question: string,
  qtype: string | undefined,
  signal: AbortSignal,
  onStep: (step: TraceStep) => void,
): Promise<QueryResult> {
  const response = await fetch("/api/stream/agentic", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, qtype }),
    signal,
  });
  if (!response.ok) throw new Error(await getApiError(response));
  if (!response.body) throw new Error("Agentic stream is unavailable");

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  let result: QueryResult | undefined;

  const readFrame = (frame: string) => {
    let eventName = "message";
    const data: string[] = [];
    for (const line of frame.split("\n")) {
      if (line.startsWith("event:")) eventName = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n")) as QueryResult | TraceStep | { code?: string };
    if (eventName === "step") onStep(payload as TraceStep);
    if (eventName === "result") result = payload as QueryResult;
    if (eventName === "error") {
      const code = "code" in payload ? payload.code : "pipeline_failed";
      throw new Error(code?.split("_").join(" ") ?? "pipeline failed");
    }
  };

  while (true) {
    const { value, done } = await reader.read();
    buffer += decoder.decode(value, { stream: !done }).replace(/\r\n/g, "\n");
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) readFrame(frame);
    if (done) {
      if (buffer.trim()) readFrame(buffer);
      break;
    }
  }

  if (!result) throw new Error("Agentic stream ended before a result was returned");
  return result;
}

function average(values: number[]): number | null {
  return values.length ? values.reduce((total, value) => total + value, 0) / values.length : null;
}

function formatValue(value: number | null, digits = 0): string {
  return value === null ? "—" : value.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: digits });
}

function formatPercent(value: number | null): string {
  return value === null ? "—" : `${formatValue(value * 100, 1)}%`;
}

export default function BenchmarkDashboard() {
  const [question, setQuestion] = useState("");
  const [qtype, setQtype] = useState("");
  const [selectedPipelines, setSelectedPipelines] = useState<PipelineId[]>(["rag", "graphrag", "agentic"]);
  const [queryResults, setQueryResults] = useState<Partial<Record<PipelineId, QueryState>>>({});
  const [queryError, setQueryError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [apiHealth, setApiHealth] = useState<ApiHealth | null>(null);
  const abortController = useRef<AbortController | null>(null);
  const [results, setResults] = useState<Partial<Record<PipelineId, PipelineResult>>>({});
  const [errors, setErrors] = useState<Partial<Record<PipelineId, string>>>({});
  const [loading, setLoading] = useState(true);
  const [refreshKey, setRefreshKey] = useState(0);

  useEffect(() => {
    let active = true;

    fetch("/api/health", { cache: "no-store" })
      .then(async (response) => {
        if (!response.ok) throw new Error("Backend unavailable");
        return await response.json() as ApiHealth;
      })
      .then((health) => { if (active) setApiHealth(health); })
      .catch(() => { if (active) setApiHealth({ ready: false, configured_pipelines: [] }); });

    async function loadResults() {
      setLoading(true);
      const nextResults: Partial<Record<PipelineId, PipelineResult>> = {};
      const nextErrors: Partial<Record<PipelineId, string>> = {};

      await Promise.all(pipelineDefinitions.map(async (pipeline) => {
        try {
          const response = await fetch(`/benchmark-results/${pipeline.file}?refresh=${refreshKey}`, { cache: "no-store" });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          nextResults[pipeline.id] = await response.json() as PipelineResult;
        } catch (error) {
          nextErrors[pipeline.id] = error instanceof Error ? error.message : "Could not load result file";
        }
      }));

      if (active) {
        setResults(nextResults);
        setErrors(nextErrors);
        setLoading(false);
      }
    }

    void loadResults();
    return () => { active = false; };
  }, [refreshKey]);

  function togglePipeline(pipeline: PipelineId) {
    setSelectedPipelines((current) => current.includes(pipeline)
      ? current.filter((item) => item !== pipeline)
      : [...current, pipeline]);
  }

  async function runQuery(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const cleanedQuestion = question.trim();
    if (!cleanedQuestion || !selectedPipelines.length || busy) return;

    const controller = new AbortController();
    abortController.current = controller;
    setBusy(true);
    setQueryError(null);
    setQueryResults((current) => {
      const next = { ...current };
      for (const pipeline of selectedPipelines) next[pipeline] = { status: "running", trace: [] };
      return next;
    });

    await Promise.all(selectedPipelines.map(async (pipeline) => {
      try {
        const result = pipeline === "agentic"
          ? await streamAgentic(cleanedQuestion, qtype || undefined, controller.signal, (step) => {
            setQueryResults((current) => {
              const state = current.agentic;
              return {
                ...current,
                agentic: { status: "running", trace: [...(state?.trace ?? []), step] },
              };
            });
          })
          : await queryPipeline(pipeline, cleanedQuestion, qtype || undefined, controller.signal);
        setQueryResults((current) => ({
          ...current,
          [pipeline]: { status: "complete", result, trace: result.trace ?? [] },
        }));
      } catch (error) {
        const cancelled = error instanceof DOMException && error.name === "AbortError";
        setQueryResults((current) => ({
          ...current,
          [pipeline]: {
            status: cancelled ? "cancelled" : "failed",
            trace: current[pipeline]?.trace ?? [],
            error: cancelled ? "Request cancelled" : error instanceof Error ? error.message : "Pipeline failed",
          },
        }));
      }
    }));

    abortController.current = null;
    setBusy(false);
  }

  function stopQuery() {
    abortController.current?.abort();
  }

  function clearQuery() {
    if (busy) return;
    setQuestion("");
    setQueryError(null);
    setQueryResults({});
  }

  const summaries = pipelineDefinitions.map((pipeline) => {
    const result = results[pipeline.id];
    const records = result?.records ?? [];
    const completed = records.filter((record) => !record.error);
    const scored = completed.filter((record) => typeof record.correct === "boolean");
    const accuracy = average(scored.map((record) => record.correct ? 1 : 0));
    const grounding = average(completed.flatMap((record) => typeof record.grounding === "number" ? [record.grounding] : []));
    const citationPrecision = average(completed.flatMap((record) => typeof record.citation_precision === "number" ? [record.citation_precision] : []));
    const citationRecall = average(completed.flatMap((record) => typeof record.citation_recall === "number" ? [record.citation_recall] : []));
    const agentSteps = average(completed.flatMap((record) => typeof record.agent_steps === "number" ? [record.agent_steps] : []));
    const tokens = average(completed.flatMap((record) => typeof record.total_tokens === "number" ? [record.total_tokens] : []));
    const latency = average(completed.flatMap((record) => typeof record.latency_seconds === "number" ? [record.latency_seconds] : []));

    return {
      ...pipeline,
      result,
      error: errors[pipeline.id],
      recordCount: result?.record_count ?? records.length,
      accuracy,
      grounding,
      citationPrecision,
      citationRecall,
      agentSteps,
      tokens,
      latency,
      failures: records.length - completed.length,
    };
  });

  const hasMeasuredResults = summaries.some((summary) => summary.recordCount > 0);
  const configuredModels = [...new Set(summaries.map((summary) => summary.result?.config?.llm_model).filter((model): model is string => Boolean(model)))];
  const modelsMatch = configuredModels.length <= 1;
  const liveSummaries = pipelineDefinitions.filter((pipeline) => selectedPipelines.includes(pipeline.id));
  const allLiveResults = liveSummaries.every((pipeline) => queryResults[pipeline.id]?.status === "complete");

  return (
    <main className="benchmark-page">
      <div className="benchmark-frame">
        <header className="benchmark-topbar">
          <Link to="/" className="benchmark-back"><ArrowLeft size={16} aria-hidden="true" /> GraphRAG</Link>
          <div className="benchmark-topbar-actions">
            <span className={`benchmark-health ${apiHealth?.ready ? "is-ready" : apiHealth ? "is-offline" : "is-checking"}`} role="status">
              <span className="benchmark-health-dot" />
              {apiHealth?.ready ? "Backend ready" : apiHealth ? "Backend unavailable" : "Checking backend"}
            </span>
            <button className="benchmark-icon-button" type="button" onClick={() => setRefreshKey((value) => value + 1)} disabled={loading} title="Refresh public results" aria-label="Refresh public results">
              <RefreshCw size={15} aria-hidden="true" className={loading ? "benchmark-spin" : ""} />
            </button>
          </div>
        </header>

        <section className="benchmark-heading">
          <div className="benchmark-eyebrow"><Activity size={15} aria-hidden="true" /> GRAPHMIND / INVESTIGATION</div>
          <h1>Pipeline comparison</h1>
          <p>Compare retrieved evidence, grounded answers, and execution cost for one question.</p>
        </section>

        <form className="benchmark-query" onSubmit={runQuery}>
          <label className="benchmark-field-label" htmlFor="benchmark-question">Question</label>
          <textarea
            id="benchmark-question"
            value={question}
            onChange={(event) => setQuestion(event.target.value)}
            placeholder="Ask a question about the corpus"
            maxLength={20_000}
            rows={3}
            required
          />
          <div className="benchmark-query-controls">
            <div className="benchmark-query-options">
              <label className="benchmark-type-label" htmlFor="benchmark-qtype">Question type</label>
              <select id="benchmark-qtype" value={qtype} onChange={(event) => setQtype(event.target.value)}>
                <option value="">Auto / unspecified</option>
                {questionTypes.map((type) => <option value={type} key={type}>{type.replace("_", " ")}</option>)}
              </select>
            </div>
            <div className="benchmark-query-buttons">
              {busy ? (
                <button className="benchmark-secondary-button" type="button" onClick={stopQuery}>
                  <Square size={15} aria-hidden="true" /> Stop
                </button>
              ) : (
                <button className="benchmark-secondary-button" type="button" onClick={clearQuery} disabled={!question && !Object.keys(queryResults).length}>
                  Clear
                </button>
              )}
              <button className="benchmark-run-button" type="submit" disabled={busy || !question.trim() || !selectedPipelines.length || !apiHealth?.ready}>
                {busy ? <LoaderCircle size={16} className="benchmark-spin" aria-hidden="true" /> : <Play size={16} aria-hidden="true" />}
                {busy ? "Running" : "Run comparison"}
              </button>
            </div>
          </div>
          <fieldset className="benchmark-pipeline-picker">
            <legend>Compare pipelines</legend>
            <div className="benchmark-segmented-control">
              {pipelineDefinitions.map((pipeline) => {
                const active = selectedPipelines.includes(pipeline.id);
                return (
                  <button
                    key={pipeline.id}
                    className={`benchmark-pipeline-option ${active ? "is-selected" : ""}`}
                    type="button"
                    aria-pressed={active}
                    onClick={() => togglePipeline(pipeline.id)}
                  >
                    {active ? <Check size={14} aria-hidden="true" /> : <span className="benchmark-option-spacer" />}
                    {pipeline.name}
                  </button>
                );
              })}
            </div>
          </fieldset>
          {!apiHealth?.ready && apiHealth && <p className="benchmark-inline-error" role="alert">The query service is not ready. Check the backend before running a comparison.</p>}
          {queryError && <p className="benchmark-inline-error" role="alert">{queryError}</p>}
        </form>

        {Object.keys(queryResults).length > 0 && (
          <section className="benchmark-live-results" aria-label="Live pipeline results">
            <div className="benchmark-section-title">
              <div><span>01</span><h2>Live results</h2></div>
              <p>{busy ? "Investigating" : allLiveResults ? "Comparison complete" : "Run state by pipeline"}</p>
            </div>
            <div className="benchmark-metric-grid">
              {liveSummaries.map((pipeline) => {
                const state = queryResults[pipeline.id];
                const result = state?.result;
                const evidence = result?.evidence ?? [];
                const trace = state?.trace ?? [];
                const paths = evidence.filter((item) => item.graph_path?.length);
                return (
                  <article className={`benchmark-pipeline benchmark-pipeline--${pipeline.accent} benchmark-pipeline-live`} key={pipeline.id}>
                    <div className="benchmark-pipeline-head">
                      <div>
                        <p className="benchmark-pipeline-kicker">{pipeline.description}</p>
                        <h2>{pipeline.name}</h2>
                      </div>
                      <span className={`benchmark-result-state state-${state?.status ?? "idle"}`}>
                        {state?.status === "running" ? <LoaderCircle size={13} className="benchmark-spin" aria-hidden="true" /> : null}
                        {state?.status ?? "idle"}
                      </span>
                    </div>
                    {state?.error && <p className="benchmark-load-error" role="alert">{state.error}</p>}
                    {result && (
                      <>
                        <p className="benchmark-answer">{result.answer}</p>
                        <div className="benchmark-live-values">
                          <div><span>Tokens</span><strong>{formatValue(result.tokens)}</strong></div>
                          <div><span>Latency</span><strong>{formatValue(result.latency, 2)}<small> s</small></strong></div>
                          <div><span>Evidence</span><strong>{formatValue(evidence.length)}</strong></div>
                          <div><span>Steps</span><strong>{formatValue(result.steps)}</strong></div>
                        </div>
                        <div className="benchmark-result-block">
                          <h3><FileText size={14} aria-hidden="true" /> Citations</h3>
                          {result.citations.length
                            ? <ul className="benchmark-citation-list">{result.citations.map((citation) => <li key={citation}>{citation}</li>)}</ul>
                            : <p className="benchmark-muted">No citations returned.</p>}
                        </div>
                        <div className="benchmark-result-block">
                          <h3><GitBranch size={14} aria-hidden="true" /> Graph paths</h3>
                          {paths.length
                            ? paths.map((item) => (
                              <div className="benchmark-graph-path" key={item.evidence_id ?? item.document_id}>
                                {item.graph_path?.map((node, index) => (
                                  <span className="benchmark-graph-node" key={`${node}-${index}`}>
                                    {index > 0 && <span className="benchmark-graph-edge" aria-hidden="true" />}{node}
                                  </span>
                                ))}
                              </div>
                            ))
                            : <p className="benchmark-muted">No graph traversal path returned.</p>}
                        </div>
                        <div className="benchmark-result-block">
                          <h3>Evidence <span className="benchmark-count">{evidence.length}</span></h3>
                          {evidence.length ? evidence.map((item, index) => (
                            <details className="benchmark-evidence" key={item.evidence_id ?? `${item.document_id}-${index}`}>
                              <summary>
                                <span>{item.document_id ?? `Evidence ${index + 1}`}</span>
                                <span>{item.retrieval_method ?? "retrieved"}{typeof item.relevance_score === "number" ? ` · ${item.relevance_score.toFixed(3)}` : ""}</span>
                              </summary>
                              <p>{item.text}</p>
                              {item.chunk_id && <small>Chunk {item.chunk_id}</small>}
                            </details>
                          )) : <p className="benchmark-muted">No evidence returned.</p>}
                        </div>
                        {pipeline.id === "agentic" && trace.length > 0 && (
                          <div className="benchmark-result-block benchmark-trace-block">
                            <h3><Activity size={14} aria-hidden="true" /> Agent trace</h3>
                            <ol className="benchmark-trace-list">
                              {trace.map((step) => (
                                <li key={step.step_id}>
                                  <span className="benchmark-trace-step">{String(step.step_id).padStart(2, "0")}</span>
                                  <div>
                                    <strong>{step.action ?? step.agent ?? "Investigation step"}</strong>
                                    <p>{step.reason ?? step.output_summary ?? step.tool ?? ""}</p>
                                    <small>{step.tool ?? "tool"}{typeof step.evidence_added === "number" ? ` · +${step.evidence_added} evidence` : ""}{typeof step.latency_seconds === "number" ? ` · ${step.latency_seconds.toFixed(2)} s` : ""}</small>
                                  </div>
                                </li>
                              ))}
                            </ol>
                          </div>
                        )}
                        <p className="benchmark-stop-reason">Stop reason: {result.stop_reason ?? "not reported"}</p>
                      </>
                    )}
                  </article>
                );
              })}
            </div>
          </section>
        )}

        {!modelsMatch && (
          <div className="benchmark-notice" role="status">
            <CircleAlert size={18} aria-hidden="true" />
            <span>Pipeline result files use different model configurations: {configuredModels.join(", ")}. Compare results cautiously.</span>
          </div>
        )}

        {!loading && !hasMeasuredResults && (
          <div className="benchmark-empty" role="status">
            <div className="benchmark-empty-icon"><Rows3 size={20} aria-hidden="true" /></div>
            <div>
              <strong>No measured benchmark results</strong>
              <p>Each public result file currently has zero records. Metrics will appear here after the three pipelines complete a public benchmark run.</p>
            </div>
          </div>
        )}

        <section className="benchmark-public-results" aria-label="Public benchmark results">
          <div className="benchmark-section-title">
            <div><span>02</span><h2>Public evaluation</h2></div>
            <p>Measured result files</p>
          </div>
          <div className="benchmark-metric-grid">
          {summaries.map((summary) => (
            <article className={`benchmark-pipeline benchmark-pipeline--${summary.accent}`} key={summary.id}>
              <div className="benchmark-pipeline-head">
                <div>
                  <p className="benchmark-pipeline-kicker">{summary.description}</p>
                  <h2>{summary.name}</h2>
                </div>
                <span className="benchmark-run-count">{loading ? "Loading" : `${summary.recordCount} records`}</span>
              </div>
              {summary.error ? <p className="benchmark-load-error">Could not load result file: {summary.error}</p> : null}
              <div className="benchmark-values">
                <div className="benchmark-value">
                  <span>Accuracy</span>
                  <strong>{formatValue(summary.accuracy === null ? null : summary.accuracy * 100, 1)}<small>{summary.accuracy === null ? "" : "%"}</small></strong>
                </div>
                <div className="benchmark-value">
                  <span>Tokens / query</span>
                  <strong>{formatValue(summary.tokens)}</strong>
                </div>
                <div className="benchmark-value">
                  <span>Avg. latency</span>
                  <strong>{formatValue(summary.latency, 2)}<small>{summary.latency === null ? "" : "s"}</small></strong>
                </div>
              </div>
              <div className="benchmark-pipeline-foot">
                <span><Zap size={14} aria-hidden="true" /> {summary.recordCount - summary.failures} completed</span>
                <span><Clock3 size={14} aria-hidden="true" /> {summary.failures} failed</span>
              </div>
            </article>
          ))}
          </div>
        </section>

        <section className="benchmark-comparison" aria-label="Side-by-side public metric comparison">
          <div className="benchmark-section-title">
            <div><span>01</span><h2>Side-by-side</h2></div>
            <p>— means no measurement is available.</p>
          </div>
          <div className="benchmark-table-wrap">
            <table>
              <thead><tr><th>Metric</th>{summaries.map((summary) => <th key={summary.id}>{summary.name}</th>)}</tr></thead>
              <tbody>
                <tr><th scope="row">Accuracy</th>{summaries.map((summary) => <td key={summary.id}>{formatValue(summary.accuracy === null ? null : summary.accuracy * 100, 1)}{summary.accuracy === null ? "" : "%"}</td>)}</tr>
                <tr><th scope="row">Grounding</th>{summaries.map((summary) => <td key={summary.id}>{formatPercent(summary.grounding)}</td>)}</tr>
                <tr><th scope="row">Citation precision</th>{summaries.map((summary) => <td key={summary.id}>{formatPercent(summary.citationPrecision)}</td>)}</tr>
                <tr><th scope="row">Citation recall</th>{summaries.map((summary) => <td key={summary.id}>{formatPercent(summary.citationRecall)}</td>)}</tr>
                <tr><th scope="row">Average tokens / query</th>{summaries.map((summary) => <td key={summary.id}>{formatValue(summary.tokens)}</td>)}</tr>
                <tr><th scope="row">Average response time</th>{summaries.map((summary) => <td key={summary.id}>{formatValue(summary.latency, 2)}{summary.latency === null ? "" : " s"}</td>)}</tr>
                <tr><th scope="row">Average agent steps</th>{summaries.map((summary) => <td key={summary.id}>{formatValue(summary.agentSteps, 1)}</td>)}</tr>
                <tr><th scope="row">Public records</th>{summaries.map((summary) => <td key={summary.id}>{loading ? "…" : summary.recordCount}</td>)}</tr>
              </tbody>
            </table>
          </div>
        </section>

        <footer className="benchmark-footer">
          <span>Source: public benchmark result files</span>
          <span>{configuredModels.length ? `Configured model: ${configuredModels.join(", ")}` : "Model configuration unavailable"}</span>
        </footer>
      </div>
    </main>
  );
}