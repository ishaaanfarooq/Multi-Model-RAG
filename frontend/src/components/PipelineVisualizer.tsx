"use client";

import { useState, useCallback } from "react";
import { WarningIcon } from "@/components/icons";

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
  const [queryInput, setQueryInput] = useState("");
  const [isRunning, setIsRunning] = useState(false);

  const runQuery = useCallback(() => {
    const query = queryInput.trim();
    if (!query || isRunning) return;

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
        console.error("Pipeline Monitor Parse Error:", err);
      }
    };

    eventSource.onerror = () => {
      setError("Lost connection to the processing pipeline. Check that the backend is running.");
      setIsRunning(false);
      eventSource.close();
    };
  }, [queryInput, isRunning]);

  const stageLabels: Record<string, string> = {
    "Master LLM Orchestrator": "Orchestrator",
    "Embedding Model": "Embedding",
    "Vector Retrieval": "Retrieval",
    "Reranking Model": "Reranking",
    Generation: "Generation",
    "Verification Module": "Verification",
    "Final Response": "Response",
  };

  return (
    <div className="flex flex-col h-full bg-cream-100">
      {/* Header */}
      <div className="px-10 py-10 bg-white border-b border-cream-300 z-10 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-ink font-heading">
            Pipeline
          </h2>
          <p className="text-xs font-medium text-stone-500 mt-1.5 uppercase tracking-widest opacity-70">
            Watch each stage of retrieval and generation in real time
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-2 px-4 py-2 bg-brass-50 border border-brass-100 rounded-full text-[10px] font-semibold text-brass-700 tracking-widest uppercase animate-pulse">
               Active
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-10">
        <div className="max-w-4xl mx-auto space-y-12">

          {/* Diagnostic Query Trigger */}
          <div className="p-8 rounded-[32px] bg-white border border-cream-300 structural-card relative overflow-hidden">
            <label className="text-[10px] font-semibold text-brass-600 uppercase tracking-[0.2em] block mb-4">
              Test query
            </label>
            <form
              onSubmit={(e) => {
                e.preventDefault();
                runQuery();
              }}
              className="flex gap-4"
            >
              <input
                type="text"
                value={queryInput}
                onChange={(e) => setQueryInput(e.target.value)}
                placeholder="Enter a query to trace through the pipeline…"
                className="input-warm flex-1 bg-white"
                disabled={isRunning}
              />
              <button
                type="submit"
                disabled={!queryInput.trim() || isRunning}
                className="btn-premium whitespace-nowrap shadow-md min-w-[140px]"
              >
                {isRunning ? "Running…" : "Run"}
              </button>
            </form>
          </div>

          {/* Stage List */}
          <div className="relative space-y-8 pb-20">
            <div className="absolute left-[34px] top-[40px] bottom-[40px] w-[2px] bg-gradient-to-b from-brass-300/40 via-cream-300 to-brass-300/40" />

            {pipeline.map((stage, i) => (
              <PipelineCard
                key={`stage-${i}`}
                stage={stage}
                index={i}
                label={stageLabels[stage.model] || stage.model}
              />
            ))}
          </div>
        </div>
      </div>

      {error && (
        <div className="fixed bottom-10 right-10 p-6 bg-brick-50 border border-brick-100 rounded-3xl shadow-2xl animate-structural-up flex items-center gap-4 z-50">
           <div className="w-10 h-10 rounded-full bg-brick-100 flex items-center justify-center text-brick-700">
             <WarningIcon className="w-5 h-5" />
           </div>
           <div>
              <p className="text-xs font-semibold text-brick-700 uppercase tracking-widest">Warning</p>
              <p className="text-sm font-medium text-brick-700 mt-0.5">{error}</p>
           </div>
        </div>
      )}
    </div>
  );
}

function PipelineCard({
  stage,
  index,
  label,
}: {
  stage: PipelineStage;
  index: number;
  label: string;
}) {
  const isProcessing = stage.status === "Processing";
  const isCompleted = stage.status === "Completed";
  const isFailed = stage.status === "Failed";
  const isWaiting = stage.status === "Waiting";

  return (
    <div
      className={`flex items-start gap-8 transition-all duration-700 ${
        isProcessing ? "scale-[1.02]" : ""
      }`}
    >
      {/* Node */}
      <div
        className={`w-[70px] h-[70px] flex-shrink-0 rounded-[28px] flex items-center justify-center text-lg font-semibold font-heading z-10 transition-all duration-700 shadow-sm border-2 ${
          isWaiting
            ? "border-cream-300 bg-white text-stone-400 opacity-50"
            : isProcessing
            ? "border-brass-500 bg-white text-brass-700 shadow-brass-900/10 scale-110"
            : isCompleted
            ? "border-sage-500 bg-white text-sage-700 shadow-sage-900/10"
            : "border-brick-500 bg-white text-brick-700 shadow-brick-900/10"
        }`}
      >
        <span>{index + 1}</span>
      </div>

      {/* Card */}
      <div
        className={`flex-1 rounded-[32px] border p-7 transition-all duration-700 relative overflow-hidden bg-white shadow-sm ${
          isProcessing
            ? "border-brass-200 shadow-xl shadow-brass-900/5 ring-4 ring-brass-50"
            : isCompleted
            ? "border-sage-200"
            : isFailed
            ? "border-brick-200"
            : "border-cream-300 opacity-50"
        }`}
      >
        {isProcessing && (
           <div className="absolute top-0 left-0 w-full h-[3px] bg-gradient-to-r from-transparent via-brass-400 to-transparent animate-[shimmer_2s_infinite]" />
        )}

        <div className="flex justify-between items-start mb-2">
          <div>
            <h3 className="text-lg font-semibold font-heading text-ink">{stage.model}</h3>
            <p className="text-[11px] font-semibold text-brass-600 uppercase tracking-[0.15em] mt-1 opacity-90">Stage {index + 1} · {label}</p>
          </div>

          <span
            className={`text-[10px] font-semibold uppercase tracking-widest px-3 py-1 rounded-full border transition-colors duration-500 ${
              isProcessing
                ? "bg-brass-50 border-brass-200 text-brass-700"
                : isCompleted
                ? "bg-sage-50 border-sage-100 text-sage-700"
                : isFailed
                ? "bg-brick-50 border-brick-100 text-brick-700"
                : "bg-cream-100 border-cream-300 text-stone-500"
            }`}
          >
            {stage.status}
          </span>
        </div>

        <p className="text-sm font-medium text-stone-600 mt-3 bg-cream-100 p-3 rounded-2xl border border-cream-300 italic">
          &quot;{stage.action}&quot;
        </p>

        {stage.details?.answer && (
          <div className="mt-5 p-5 rounded-2xl bg-ink text-brass-100 text-xs font-medium leading-[1.7] shadow-inner overflow-hidden relative">
            <div className="absolute top-2 right-4 text-[9px] uppercase tracking-widest text-brass-300/60 font-semibold">Raw response</div>
            <div className="font-mono">{stage.details.answer}</div>
          </div>
        )}
      </div>
    </div>
  );
}
