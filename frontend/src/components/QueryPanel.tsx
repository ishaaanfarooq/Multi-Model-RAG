"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  chart?: string;
  warning?: string;
  timestamp: Date;
  pipeline?: PipelineStage[];
};

type PipelineStage = {
  model: string;
  status: string;
  action: string;
  details?: any;
};

// Moving StageDisplay outside the component to prevent re-creation on every render
const StageDisplay = ({ stages }: { stages: PipelineStage[] }) => (
  <div className="flex flex-col gap-2 p-4 bg-[#FAF9F6] border border-[#F1F1EF] rounded-3xl mt-4 max-w-[500px]">
    <p className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.1em] mb-2 opacity-80">Pipeline Execution Path</p>
    {stages.map((stage, i) => (
      <div key={i} className="flex items-center gap-3 text-[11px] font-medium text-[#71717A]">
        <span className={`w-1.5 h-1.5 rounded-full ${
          stage.status === 'Processing' ? 'bg-[#FF9100] animate-pulse' : 
          stage.status === 'Completed' ? 'bg-[#16A34A]' : 'bg-[#E4E4E5]'
        }`} />
        <span className="text-[#18181B] font-bold min-w-[140px] text-xs">{stage.model}</span>
        <span className="truncate opacity-70 italic">{stage.action}</span>
      </div>
    ))}
  </div>
);

export default function QueryPanel() {
  const [hasMounted, setHasMounted] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveStages, setLiveStages] = useState<PipelineStage[]>([]);
  
  useEffect(() => {
    setHasMounted(true);
    setMessages([
      {
        id: "welcome",
        role: "system",
        content:
          "Welcome to your Professional AI Workspace. Please upload your knowledge base documents or crawl your target websites to begin. What can I help you analyze today?",
        timestamp: new Date(),
      },
    ]);
  }, []);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  
  // Use a ref for liveStages to capture them in the SSE callback without re-creating handleSend
  const stagesRef = useRef<PipelineStage[]>([]);

  useEffect(() => {
    stagesRef.current = liveStages;
  }, [liveStages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, liveStages]);

  const handleSend = useCallback(() => {
    const query = input.trim();
    if (!query || isProcessing) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: query,
      timestamp: new Date(),
    };
    
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsProcessing(true);
    setLiveStages([]);

    console.log("[QueryPanel] handleSend triggered for:", query);
    console.log("[QueryPanel] Connecting to EventSource:", `${API_BASE}/api/stream?query=${encodeURIComponent(query)}`);

    const eventSource = new EventSource(
      `${API_BASE}/api/stream?query=${encodeURIComponent(query)}`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);


        if (data.model === "Final Response" && data.status === "Completed") {
          setMessages((prev) => {
            const aiMsg: Message = {
              id: (Date.now() + 1).toString(),
              role: "assistant",
              content: data.details?.answer || "Analytical synthesis produced no tangible result.",
              sources: data.details?.sources || [],
              chart: data.details?.chart || undefined,
              warning: data.details?.warning || undefined,
              timestamp: new Date(),
              // Combine liveStages with the final response data directly
              pipeline: [...stagesRef.current, data].map(stage => 
                stage.model === data.model ? data : stage
              ),
            };
            return [...prev, aiMsg];
          });
          
          setIsProcessing(false);
          setLiveStages([]);
          eventSource.close();
        } else {
          // Update live stages for all other events
          setLiveStages((prev) => {
            const idx = prev.findIndex((s) => s.model === data.model);
            if (idx >= 0) {
              const updated = [...prev];
              updated[idx] = data;
              return updated;
            }
            return [...prev, data];
          });
        }
      } catch (err) {
        console.error("Critical SSE parse error:", err);
      }
    };

    eventSource.onerror = () => {
      const errorMsg: Message = {
        id: (Date.now() + 2).toString(),
        role: "system",
        content: "Network integrity compromised. Ensure your local framework host is active on Port 8000.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setIsProcessing(false);
      setLiveStages([]);
      eventSource.close();
    };
  }, [input, isProcessing]); // Removed liveStages from dependencies

  return (
    <div className="flex flex-col h-full bg-white relative min-h-0">
      {/* Structural Header */}
      <div className="px-10 py-8 border-b border-[#F1F1EF] bg-white z-10 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[#18181B] font-heading">
            Neural Analysis Interface
          </h2>
          <p className="text-xs font-medium text-[#71717A] mt-1.5 uppercase tracking-wide opacity-60">
            Professional Multi-Agent Retrieval Framework
          </p>
        </div>
        <div className="flex items-center gap-4">
           {isProcessing && (
              <div className="flex items-center gap-2 group relative">
                <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-100 rounded-full text-[11px] font-bold text-amber-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-600 animate-ping" />
                  Processing
                </div>
                <button 
                  onClick={() => setIsProcessing(false)}
                  className="hidden group-hover:block absolute right-0 top-full mt-2 px-2 py-1 bg-red-50 text-red-600 text-[9px] font-bold rounded border border-red-100 whitespace-nowrap shadow-sm z-50"
                >
                  Force Reset ❌
                </button>
              </div>
           )}
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto px-10 py-10 space-y-8">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} animate-structural-up`}
          >
            <div
              className={`max-w-[800px] ${
                msg.role === "user" ? "bubble-user" : 
                msg.role === "system" ? "text-center mx-auto text-[11px] text-[#71717A] italic opacity-60 py-4 max-w-[400px]" : 
                "bubble-ai"
              }`}
            >
              <div className="relative">
                {msg.role === "assistant" && msg.pipeline && (
                  <StageDisplay stages={msg.pipeline} />
                )}
                
                <div className={`text-[15px] leading-[1.65] font-medium ${msg.role === "assistant" ? "mt-4 text-[#27272A] prose prose-zinc max-w-none prose-sm prose-headings:mb-2 prose-p:mb-2 prose-table:border prose-table:border-zinc-200 prose-th:bg-zinc-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2" : ""}`}>
                  {msg.role === "assistant" ? (
                    <ReactMarkdown remarkPlugins={[remarkGfm]}>
                      {msg.content}
                    </ReactMarkdown>
                  ) : (
                    msg.content
                  )}
                </div>

                {msg.chart && (
                  <div className="mt-6 p-4 bg-[#FAF9F6] border border-[#F1F1EF] rounded-2xl overflow-hidden group/chart">
                    <p className="text-[10px] uppercase font-bold text-[#B45309] tracking-widest mb-3 opacity-60">Generated Analytical Visualization</p>
                    <img 
                      src={msg.chart.startsWith('http') ? msg.chart : `${API_BASE}${msg.chart}`} 
                      alt="Analytical Chart"
                      className="w-full h-auto rounded-xl shadow-sm border border-amber-100 group-hover/chart:scale-[1.01] transition-transform duration-500"
                    />
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[9px] font-bold text-[#71717A] uppercase tracking-tighter italic">PaperBanana-style Synthetic Rendering</span>
                      <a 
                        href={msg.chart.startsWith('http') ? msg.chart : `${API_BASE}${msg.chart}`} 
                        target="_blank" 
                        rel="noreferrer"
                        className="text-[10px] font-bold text-[#B45309] hover:underline"
                      >
                        View High Resolution →
                      </a>
                    </div>
                  </div>
                )}
                
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-6 pt-4 border-t border-[#F1F1EF]">
                    <p className="text-[10px] uppercase font-bold text-[#B45309] tracking-widest mb-3">
                      Verification Ingress Sources
                    </p>
                    <div className="flex flex-wrap gap-2">
                      {msg.sources.map((src, i) => (
                        <a key={i} href={src} target="_blank" rel="noreferrer"
                          className="px-2 py-1 bg-[#FAF9F6] border border-[#F1F1EF] text-[#71717A] rounded-lg text-[10px] font-bold hover:border-amber-300 hover:text-amber-700 transition-colors truncate max-w-[260px]"
                          title={src}>
                          {src.replace(/^https?:\/\//, "").split("/")[0]}
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {msg.warning && (
                  <div className="mt-4 flex items-start gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-2xl">
                    <span className="text-lg mt-0.5">⚠️</span>
                    <div>
                      <p className="text-[10px] uppercase font-bold text-amber-700 tracking-widest mb-1">Accuracy Notice</p>
                      <p className="text-[12px] text-amber-800 leading-relaxed">{msg.warning}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <span className="text-[10px] text-[#A1A1AA] font-bold mt-2 px-2 uppercase tracking-tighter opacity-50">
              {msg.role} • {hasMounted && msg.timestamp instanceof Date ? msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recently"}
            </span>
          </div>
        ))}

        {/* Live Pipeline Processing Module */}
        {isProcessing && (
          <div className="flex flex-col items-start animate-structural-up">
             <div className="bubble-ai border-amber-200/50 bg-[#FFFCF8]">
                <div className="flex items-center gap-3 mb-4">
                   <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                   <span className="text-[11px] font-bold text-amber-700 uppercase tracking-widest">Active Neural Routing...</span>
                </div>
                <StageDisplay stages={liveStages} />
             </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Structural Input Area */}
      <div className="px-10 py-10 border-t border-[#F1F1EF] bg-white">
        <div className="max-w-4xl mx-auto relative group">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-4 items-center bg-[#FCFBFA] border-2 border-[#F1F1EF] p-2 pr-4 rounded-[28px] focus-within:border-[#B45309] focus-within:bg-white shadow-sm transition-all duration-300"
          >
            <div className="w-12 h-12 rounded-full bg-[#FAF9F6] flex items-center justify-center text-xl text-[#B45309]">✨</div>
            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Submit query to the MultiModel RAG Framework..."
              className="flex-1 bg-transparent border-none outline-none text-[#18181B] font-medium text-[15px] placeholder:text-[#A1A1AA]"
              disabled={isProcessing}
            />
            <button
              type="submit"
              disabled={!input.trim()}
              className="btn-premium rounded-[20px] py-3 shadow-md"
            >
              {isProcessing ? "Processing..." : "Analyze →"}
            </button>
          </form>
          <p className="text-[10px] font-bold text-[#71717A] text-center mt-4 uppercase tracking-[0.2em] opacity-40">
            Secured Contextual Retrieval • Local Intelligence
          </p>
        </div>
      </div>
    </div>
  );
}
