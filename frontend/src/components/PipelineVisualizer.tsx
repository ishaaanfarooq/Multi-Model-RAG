"use client";

import { useEffect, useState, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export type PipelineStage = {
  model: string;
  status: "Waiting" | "Processing" | "Completed" | "Failed";
  action: string;
  details?: any;
};

const initialPipeline: PipelineStage[] = [
  { model: "Master LLM Orchestrator", status: "Waiting", action: "Awaiting query" },
  { model: "Embedding Model", status: "Waiting", action: "Awaiting text" },
  { model: "Vector Retrieval", status: "Waiting", action: "Awaiting vectors" },
  { model: "Reranking Model", status: "Waiting", action: "Awaiting documents" },
  { model: "Generation", status: "Waiting", action: "Awaiting context" },
  { model: "Verification Module", status: "Waiting", action: "Awaiting draft" },
  { model: "Final Response", status: "Waiting", action: "Pending" },
];

export default function PipelineVisualizer() {
  const [pipeline, setPipeline] = useState<PipelineStage[]>(initialPipeline);
  const [error, setError] = useState<string | null>(null);
  const [lastQuery, setLastQuery] = useState<string | null>(null);
  const [queryInput, setQueryInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const runQuery = useCallback(() => {
    const query = queryInput.trim();
    if (!query || isRunning) return;

    setLastQuery(query);
    setPipeline(initialPipeline.map((p) => ({ ...p, status: "Waiting" })));
    setError(null);
    setIsRunning(true);

    const eventSource = new EventSource(
      `${API_BASE}/api/stream?query=${encodeURIComponent(query)}`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setPipeline((prev) => {
          const newPipeline = [...prev];
          const stageIndex = newPipeline.findIndex((p) => p.model === data.model);
          if (stageIndex >= 0) {
            newPipeline[stageIndex] = {
              ...newPipeline[stageIndex],
              status: data.status,
              action: data.action,
              details: data.details,
            };
          }
          return newPipeline;
        });

        if (data.model === "Final Response" && data.status === "Completed") {
          setIsRunning(false);
          eventSource.close();
        }
      } catch (err) {
        console.error("Error parsing SSE:", err);
      }
    };

    eventSource.onerror = () => {
      setError("Lost connection to processing pipeline.");
      setIsRunning(false);
      eventSource.close();
    };
  }, [queryInput, isRunning]);

  const stageIcons: Record<string, string> = {
    "Master LLM Orchestrator": "🧠",
    "Embedding Model": "🔢",
    "Vector Retrieval": "🔍",
    "Reranking Model": "📊",
    Generation: "✨",
    "Verification Module": "🛡️",
    "Final Response": "🎯",
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--color-border)]">
        <h2 className="text-xl font-bold tracking-tight">⚡ Pipeline Monitor</h2>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          Watch each stage of the RAG pipeline execute in real-time
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Query Input */}
        <div className="glass-panel-solid p-5">
          <label className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider block mb-2">
            Run a query through the pipeline
          </label>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              runQuery();
            }}
            className="flex gap-3"
          >
            <input
              type="text"
              value={queryInput}
              onChange={(e) => setQueryInput(e.target.value)}
              placeholder="Enter your query to visualize the pipeline..."
              className="input-dark flex-1"
              disabled={isRunning}
            />
            <button
              type="submit"
              disabled={!queryInput.trim() || isRunning}
              className="btn-primary whitespace-nowrap"
            >
              {isRunning ? "Running..." : "Execute ⚡"}
            </button>
          </form>
        </div>

        {/* Pipeline Header */}
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-[var(--color-muted)] uppercase tracking-wider">
            Pipeline Stages
          </h3>
          {isRunning && (
            <span className="badge badge-warning animate-pulse">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)]" />
              Running
            </span>
          )}
          {lastQuery && !isRunning && pipeline.some((p) => p.status === "Completed") && (
            <span className="badge badge-success">
              <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-success)]" />
              Complete
            </span>
          )}
        </div>

        {/* Error */}
        {error && (
          <div className="glass-panel p-4 animate-slide-up" style={{ borderColor: "var(--color-error)" }}>
            <p className="text-sm text-[var(--color-error)]">⚠️ {error}</p>
          </div>
        )}

        {/* Pipeline Cards */}
        <div className="relative">
          {/* Connecting line */}
          <div className="absolute left-[23px] top-[30px] bottom-[30px] w-[2px] bg-[var(--color-border)]" />

          <div className="flex flex-col gap-3 relative z-10">
            {pipeline.map((stage, i) => (
              <PipelineCard
                key={`stage-${i}`}
                stage={stage}
                index={i}
                icon={stageIcons[stage.model] || "•"}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

function PipelineCard({
  stage,
  index,
  icon,
}: {
  stage: PipelineStage;
  index: number;
  icon: string;
}) {
  const isProcessing = stage.status === "Processing";
  const isCompleted = stage.status === "Completed";
  const isFailed = stage.status === "Failed";
  const isWaiting = stage.status === "Waiting";

  const getCardClass = () => {
    if (isProcessing)
      return "border-[var(--color-warning)] bg-[rgba(245,158,11,0.05)] glow-warning";
    if (isCompleted)
      return "border-[var(--color-success)] bg-[rgba(34,197,94,0.05)] glow-success";
    if (isFailed) return "border-[var(--color-error)] bg-[rgba(239,68,68,0.05)] glow-error";
    return "border-[var(--color-border)] bg-[var(--color-surface)] opacity-50";
  };

  const getIndicator = () => {
    if (isProcessing) return "bg-[var(--color-warning)] animate-pulse shadow-[0_0_10px_var(--color-warning)]";
    if (isCompleted) return "bg-[var(--color-success)] shadow-[0_0_10px_var(--color-success)]";
    if (isFailed) return "bg-[var(--color-error)] shadow-[0_0_10px_var(--color-error)]";
    return "bg-[var(--color-border-bright)]";
  };

  return (
    <div
      className={`flex items-start gap-4 transition-all duration-500 ${
        isProcessing ? "scale-[1.01]" : ""
      }`}
    >
      {/* Node */}
      <div
        className={`w-[46px] h-[46px] flex-shrink-0 rounded-xl flex items-center justify-center border-2 z-10 transition-all duration-500 ${
          isWaiting
            ? "border-[var(--color-border)] bg-[var(--color-surface)]"
            : isProcessing
            ? "border-[var(--color-warning)] bg-[rgba(245,158,11,0.1)]"
            : isCompleted
            ? "border-[var(--color-success)] bg-[rgba(34,197,94,0.1)]"
            : "border-[var(--color-error)] bg-[rgba(239,68,68,0.1)]"
        }`}
      >
        <span className="text-lg">{icon}</span>
      </div>

      {/* Card */}
      <div
        className={`flex-1 rounded-xl border p-4 transition-all duration-500 ${getCardClass()}`}
      >
        <div className="flex justify-between items-center mb-1">
          <h3 className="text-sm font-bold">{stage.model}</h3>
          <div className="flex items-center gap-2">
            <div className={`w-2 h-2 rounded-full ${getIndicator()}`} />
            <span
              className={`text-[10px] font-semibold uppercase tracking-wider ${
                isProcessing
                  ? "text-[var(--color-warning)]"
                  : isCompleted
                  ? "text-[var(--color-success)]"
                  : isFailed
                  ? "text-[var(--color-error)]"
                  : "text-[var(--color-muted)]"
              }`}
            >
              {stage.status}
            </span>
          </div>
        </div>
        <p className="text-xs text-[var(--color-muted)]">{stage.action}</p>

        {stage.details?.answer && (
          <div className="mt-3 p-3 rounded-lg bg-[var(--color-background)] border border-[var(--color-border)] text-sm whitespace-pre-wrap leading-relaxed">
            {stage.details.answer}
          </div>
        )}
      </div>
    </div>
  );
}
