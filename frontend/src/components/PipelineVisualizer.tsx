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
        console.error("Pipeline Monitor Parse Error:", err);
      }
    };

    eventSource.onerror = () => {
      setError("Lost connection to processing pipeline. Check backend integrity.");
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
    <div className="flex flex-col h-full bg-[#FAF9F6]">
      {/* Header Container */}
      <div className="px-10 py-10 bg-white border-b border-[#F1F1EF] z-10 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[#18181B] font-heading">
            Pipeline Observatory
          </h2>
          <p className="text-xs font-semibold text-[#71717A] mt-1.5 uppercase tracking-widest opacity-60">
            Real-time multi-agent execution telemetry
          </p>
        </div>
        <div className="flex items-center gap-3">
          {isRunning && (
            <div className="flex items-center gap-2 px-4 py-2 bg-amber-50 border border-amber-100 rounded-full text-[10px] font-bold text-amber-700 tracking-widest uppercase animate-pulse">
               Active
            </div>
          )}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-10">
        <div className="max-w-4xl mx-auto space-y-12">
          
          {/* Diagnostic Query Trigger */}
          <div className="p-8 rounded-[32px] bg-white border border-[#F1F1EF] structural-card relative overflow-hidden group">
            <div className="absolute top-0 right-0 p-4 opacity-[0.03] transition-opacity duration-500 group-hover:opacity-[0.06]">
               <span className="text-9xl transition-transform duration-700 group-hover:scale-110">🩺</span>
            </div>
            <div className="relative z-10">
              <label className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.2em] block mb-4">
                Manual Pipeline Diagnostic
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
                  placeholder="Enter a test query to monitor the neural stack..."
                  className="input-warm flex-1 bg-white"
                  disabled={isRunning}
                />
                <button
                  type="submit"
                  disabled={!queryInput.trim() || isRunning}
                  className="btn-premium whitespace-nowrap shadow-md min-w-[140px]"
                >
                  {isRunning ? "Monitoring" : "Run Diagnostic"}
                </button>
              </form>
            </div>
          </div>

          {/* Telemetry Stage Hierarchy */}
          <div className="relative space-y-8 pb-20">
            {/* Visual Continuity Spine */}
            <div className="absolute left-[34px] top-[40px] bottom-[40px] w-[2px] bg-gradient-to-b from-amber-700/20 via-zinc-200 to-amber-700/20" />

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

      {error && (
        <div className="fixed bottom-10 right-10 p-6 bg-red-50 border border-red-100 rounded-3xl shadow-2xl animate-structural-up flex items-center gap-4 z-50">
           <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center text-red-600">⚠️</div>
           <div>
              <p className="text-xs font-bold text-red-700 uppercase tracking-widest">System Warning</p>
              <p className="text-sm font-medium text-red-900 mt-0.5">{error}</p>
           </div>
        </div>
      )}
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

  return (
    <div
      className={`flex items-start gap-8 transition-all duration-700 ${
        isProcessing ? "scale-[1.02]" : ""
      }`}
    >
      {/* Neural Node */}
      <div
        className={`w-[70px] h-[70px] flex-shrink-0 rounded-[28px] flex items-center justify-center text-2xl z-10 transition-all duration-700 shadow-sm border-2 ${
          isWaiting
            ? "border-[#F1F1EF] bg-white opacity-40 grayscale"
            : isProcessing
            ? "border-[#B45309] bg-white shadow-amber-900/10 scale-110"
            : isCompleted
            ? "border-[#15803D] bg-white shadow-green-900/10"
            : "border-[#DC2626] bg-white shadow-red-900/10"
        }`}
      >
        <span>{icon}</span>
      </div>

      {/* Observation Module */}
      <div
        className={`flex-1 rounded-[32px] border p-7 transition-all duration-700 relative overflow-hidden bg-white shadow-sm ${
          isProcessing
            ? "border-amber-200 shadow-xl shadow-amber-900/5 ring-4 ring-amber-50"
            : isCompleted
            ? "border-green-200"
            : isFailed
            ? "border-red-200"
            : "border-[#F1F1EF] opacity-40"
        }`}
      >
        {isProcessing && (
           <div className="absolute top-0 left-0 w-full h-[3px] bg-gradient-to-r from-transparent via-amber-500 to-transparent animate-[shimmer_2s_infinite]" />
        )}

        <div className="flex justify-between items-start mb-2">
          <div>
            <h3 className="text-lg font-bold font-heading text-[#18181B]">{stage.model}</h3>
            <p className="text-[11px] font-bold text-[#B45309] uppercase tracking-[0.15em] mt-1 opacity-80">Agent Module {index + 1}</p>
          </div>
          
          <div className="flex items-center gap-2 group cursor-help">
            <span
              className={`text-[10px] font-bold uppercase tracking-widest px-3 py-1 rounded-full border transition-colors duration-500 ${
                isProcessing
                  ? "bg-amber-50 border-amber-200 text-amber-700"
                  : isCompleted
                  ? "bg-green-50 border-green-200 text-green-700"
                  : isFailed
                  ? "bg-red-50 border-red-200 text-red-700"
                  : "bg-zinc-50 border-zinc-200 text-[#71717A]"
              }`}
            >
              {stage.status}
            </span>
          </div>
        </div>
        
        <p className="text-sm font-medium text-[#71717A] mt-3 bg-[#FAF9F6] p-3 rounded-2xl border border-[#F1F1EF] italic">
          &quot;{stage.action}&quot;
        </p>

        {stage.details?.answer && (
          <div className="mt-5 p-5 rounded-2xl bg-zinc-950 text-amber-50 text-xs font-medium leading-[1.7] shadow-inner overflow-hidden relative">
            <div className="absolute top-2 right-4 text-[9px] uppercase tracking-widest text-amber-500/50 font-bold">Encrypted Telemetry JSON</div>
            <div className="font-mono">{stage.details.answer}</div>
          </div>
        )}
      </div>
    </div>
  );
}
