"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  timestamp: Date;
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
        "Welcome to MultiModel RAG. Upload documents or crawl a website first, then ask questions about the ingested content.",
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
            content: data.details?.answer || "No response generated.",
            sources: data.details?.sources || [],
            timestamp: new Date(),
          };
          setMessages((prev) => [...prev, aiMsg]);
          setIsProcessing(false);
          setLiveStages([]);
          eventSource.close();
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    eventSource.onerror = () => {
      const errorMsg: Message = {
        id: (Date.now() + 2).toString(),
        role: "system",
        content: "Connection lost. Make sure the backend server is running on port 8000.",
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
      setIsProcessing(false);
      setLiveStages([]);
      eventSource.close();
    };
  }, [input, isProcessing]);

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--color-border)]">
        <h2 className="text-xl font-bold tracking-tight">💬 Chat with your Knowledge Base</h2>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          Ask questions about your ingested documents and crawled websites
        </p>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-6 py-4 space-y-4">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`animate-slide-up ${
              msg.role === "user" ? "flex justify-end" : "flex justify-start"
            }`}
          >
            <div
              className={`max-w-[75%] rounded-2xl px-5 py-3 ${
                msg.role === "user"
                  ? "accent-gradient text-white"
                  : msg.role === "system"
                  ? "bg-[var(--color-surface-hover)] border border-[var(--color-border)] text-[var(--color-muted)]"
                  : "glass-panel-solid"
              }`}
            >
              <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
              {msg.sources && msg.sources.length > 0 && (
                <div className="mt-3 pt-2 border-t border-[var(--color-border)]">
                  <p className="text-[10px] uppercase font-semibold text-[var(--color-muted)] tracking-wider mb-1">
                    Sources
                  </p>
                  <div className="flex flex-wrap gap-1.5">
                    {msg.sources.map((src, i) => (
                      <span key={i} className="badge badge-info text-[10px]">
                        {src}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        ))}

        {/* Live Pipeline Stages */}
        {isProcessing && liveStages.length > 0 && (
          <div className="animate-slide-up glass-panel p-4 space-y-2">
            <p className="text-xs font-semibold text-[var(--color-accent)] uppercase tracking-wider">
              Pipeline Processing...
            </p>
            {liveStages.map((stage, i) => (
              <div
                key={i}
                className="flex items-center gap-3 text-xs"
              >
                <div
                  className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    stage.status === "Processing"
                      ? "bg-[var(--color-warning)] animate-pulse"
                      : stage.status === "Completed"
                      ? "bg-[var(--color-success)]"
                      : "bg-[var(--color-muted)]"
                  }`}
                />
                <span className="font-medium text-[var(--color-foreground)]">
                  {stage.model}
                </span>
                <span className="text-[var(--color-muted)] truncate">{stage.action}</span>
              </div>
            ))}
          </div>
        )}

        {isProcessing && liveStages.length === 0 && (
          <div className="flex justify-start animate-slide-up">
            <div className="glass-panel px-5 py-3">
              <div className="flex gap-1.5">
                <div className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: "0ms" }} />
                <div className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: "150ms" }} />
                <div className="w-2 h-2 rounded-full bg-[var(--color-accent)] animate-bounce" style={{ animationDelay: "300ms" }} />
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input Bar */}
      <div className="px-6 py-4 border-t border-[var(--color-border)]">
        <form
          onSubmit={(e) => {
            e.preventDefault();
            handleSend();
          }}
          className="flex gap-3"
        >
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Ask a question about your documents..."
            className="input-dark flex-1"
            disabled={isProcessing}
          />
          <button
            type="submit"
            disabled={!input.trim() || isProcessing}
            className="btn-primary whitespace-nowrap"
          >
            {isProcessing ? "Processing..." : "Send →"}
          </button>
        </form>
      </div>
    </div>
  );
}
