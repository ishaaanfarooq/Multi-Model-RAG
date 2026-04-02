"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  timestamp: Date;
  pipeline?: PipelineStage[];
};

type PipelineStage = {
  model: string;
  status: string;
  action: string;
};

export default function QueryPanel() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "system",
      content:
        "Welcome to your Professional AI Workspace. Please upload your knowledge base documents or crawl your target websites to begin. What can I help you analyze today?",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveStages, setLiveStages] = useState<PipelineStage[]>([]);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

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

    const eventSource = new EventSource(
      `${API_BASE}/api/stream?query=${encodeURIComponent(query)}`
    );

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);

        setLiveStages((prev) => {
          const idx = prev.findIndex((s) => s.model === data.model);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = data;
            return updated;
          }
          return [...prev, data];
        });

        if (data.model === "Final Response" && data.status === "Completed") {
          const aiMsg: Message = {
            id: (Date.now() + 1).toString(),
            role: "assistant",
            content: data.details?.answer || "Analytical synthesis produced no tangible result.",
            sources: data.details?.sources || [],
            timestamp: new Date(),
            pipeline: [...liveStages, data],
          };
          setMessages((prev) => [...prev, aiMsg]);
          setIsProcessing(false);
          setLiveStages([]);
          eventSource.close();
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
  }, [input, isProcessing, liveStages]);

  const StageDisplay = ({ stages }: { stages: PipelineStage[] }) => (
    <div className="flex flex-col gap-2 p-4 bg-[#FAF9F6] border border-[#F1F1EF] rounded-3xl mt-4 max-w-[500px]">
      <p className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.1em] mb-2 opacity-80">Pipeline Execution Path</p>
      {stages.map((stage, i) => (
        <div key={i} className="flex items-center gap-3 text-[11px] font-medium text-[#71717A]">
          <span className={`w-1.5 h-1.5 rounded-full ${
            stage.status === 'Processing' ? 'bg-[#FF9100] animate-pulse' : 
            stage.status === 'Completed' ? 'bg-[#16A34A]' : 'bg-[#E4E4E5]'
          }`} />
          <span className="text-[#18181B] font-bold min-w-[140px]">{stage.model}</span>
          <span className="truncate opacity-70 italic">{stage.action}</span>
        </div>
      ))}
    </div>
  );

  return (
    <div className="flex flex-col h-full bg-white relative">
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
              <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-100 rounded-full text-[11px] font-bold text-amber-700">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-600 animate-ping" />
                Processing
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
              {msg.role === "assistant" && msg.pipeline && (
                <StageDisplay stages={msg.pipeline} />
              )}
              <div className={`text-[15px] leading-[1.65] font-medium ${msg.role === "assistant" ? "mt-4 text-[#27272A]" : ""}`}>
                {msg.content}
              </div>
              
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-6 pt-4 border-t border-[#F1F1EF]">
                  <p className="text-[10px] uppercase font-bold text-[#B45309] tracking-widest mb-3">
                    Verification Ingress Sources
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {msg.sources.map((src, i) => (
                      <span key={i} className="px-2 py-1 bg-[#FAF9F6] border border-[#F1F1EF] text-[#71717A] rounded-lg text-[10px] font-bold">
                        {src}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
            <span className="text-[10px] text-[#A1A1AA] font-bold mt-2 px-2 uppercase tracking-tighter opacity-50">
              {msg.role} • {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
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
              disabled={!input.trim() || isProcessing}
              className="btn-premium rounded-[20px] py-3 shadow-md"
            >
              {isProcessing ? "Processing" : "Analyze →"}
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
