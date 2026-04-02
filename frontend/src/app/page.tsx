"use client";

import { useState, useRef, useEffect, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type PipelineStage = {
  model: string;
  status: string;
  action: string;
};

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  pipeline?: PipelineStage[];
};

export default function UnifiedPage() {
  const [messages, setMessages] = useState<Message[]>([
    {
      id: "welcome",
      role: "system",
      content: "Welcome to MultiModel RAG! Paste a website URL above to crawl and index it into the knowledge base, then ask me anything.",
    },
  ]);
  
  // Crawl State
  const [url, setUrl] = useState("");
  const [isCrawling, setIsCrawling] = useState(false);
  const [crawlStats, setCrawlStats] = useState({ pages: 0, chunks: 0, status: "" });
  
  // Chat State
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveStages, setLiveStages] = useState<PipelineStage[]>([]);
  
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, liveStages, crawlStats]);

  const handleCrawl = useCallback(() => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl || isCrawling) return;
    try { new URL(trimmedUrl); } catch { alert("Invalid URL. Please include http:// or https://"); return; }
    
    setIsCrawling(true);
    setCrawlStats({ pages: 0, chunks: 0, status: "Initializing..." });
    
    const params = new URLSearchParams({ url: trimmedUrl, max_pages: "15", max_depth: "2" });
    const eventSource = new EventSource(`${API_BASE}/api/crawl/stream?${params}`);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.status === "completed" || data.status === "ingested") {
          setCrawlStats({ pages: data.pages_done || 0, chunks: data.total_chunks || 0, status: "Complete" });
        } else {
          setCrawlStats(prev => ({ ...prev, pages: data.pages_done || prev.pages, status: data.message || prev.status }));
        }
        if (data.status === "ingested" || data.status === "error") {
          setIsCrawling(false);
          eventSource.close();
        }
      } catch (err) {}
    };
    eventSource.onerror = () => { setIsCrawling(false); eventSource.close(); };
  }, [url, isCrawling]);

  const handleSend = useCallback(() => {
    const query = input.trim();
    if (!query || isProcessing) return;
    
    const userMessages = messages.filter(m => m.role === 'user').map(m => m.content).slice(-2);
    const historyParam = userMessages.length > 0 ? `&history=${encodeURIComponent(userMessages.join(' | '))}` : '';
    
    setMessages(prev => [...prev, { id: Date.now().toString(), role: "user", content: query }]);
    setInput("");
    setIsProcessing(true);
    setLiveStages([]);
    
    const eventSource = new EventSource(`${API_BASE}/api/stream?query=${encodeURIComponent(query)}${historyParam}`);
    
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setLiveStages(prev => {
          const idx = prev.findIndex(s => s.model === data.model);
          if (idx >= 0) {
            const updated = [...prev];
            updated[idx] = data;
            return updated;
          }
          return [...prev, data];
        });
        
        if (data.model === "Final Response" && data.status === "Completed") {
          setMessages(prev => [...prev, {
            id: (Date.now() + 1).toString(),
            role: "assistant",
            content: data.details?.answer || "No response generated.",
            sources: data.details?.sources || [],
          }]);
          setIsProcessing(false);
          eventSource.close();
        }
      } catch (err) {}
    };
    
    eventSource.onerror = () => {
      setIsProcessing(false);
      eventSource.close();
    };
  }, [input, isProcessing]);

  // Safely attach pipeline stages to the message after it finishes processing
  useEffect(() => {
    if (!isProcessing && liveStages.length > 0) {
       setMessages(prev => {
           const newMsg = [...prev];
           const lastMsg = newMsg[newMsg.length - 1];
           if (lastMsg && lastMsg.role === "assistant" && !lastMsg.pipeline) {
               lastMsg.pipeline = [...liveStages];
           }
           return newMsg;
       });
       setLiveStages([]);
    }
  }, [isProcessing, liveStages]);

  const StageIndicator = ({ stage }: { stage: PipelineStage }) => (
    <div className="flex items-center gap-3 text-[10px] sm:text-xs">
      <div className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${
        stage.status === "Processing" ? "bg-[var(--color-warning)] animate-pulse" :
        stage.status === "Completed" ? "bg-[var(--color-success)]" : "bg-[var(--color-muted)]"
      }`} />
      <span className="font-semibold text-[var(--color-foreground)] min-w-[120px]">{stage.model}</span>
      <span className="text-[var(--color-muted)] truncate">{stage.action}</span>
    </div>
  );

  return (
    <div className="flex flex-col h-screen overflow-hidden bg-[#0a0a0f] font-sans">
      {/* Top Banner & Crawler Interface */}
      <div className="px-6 py-4 border-b border-[var(--color-border)] bg-[var(--color-surface)] z-10 shadow-sm shadow-black/50">
        <div className="flex flex-col sm:flex-row items-center gap-4 max-w-5xl mx-auto w-full">
          <div className="font-bold text-xl accent-gradient-text tracking-tight whitespace-nowrap">
            MultiModel RAG
          </div>
          
          <div className="h-8 w-px bg-[var(--color-border)] hidden sm:block"></div>
          
          <div className="flex-1 w-full flex gap-2">
            <input 
              type="url" value={url} onChange={e => setUrl(e.target.value)}
              placeholder="Paste website URL to crawl..."
              className="input-dark flex-1 h-10 py-0" disabled={isCrawling}
            />
            <button onClick={handleCrawl} disabled={!url.trim() || isCrawling} className="btn-primary h-10 py-0 px-4 whitespace-nowrap">
              {isCrawling ? "Crawling..." : "Index Website 🌐"}
            </button>
          </div>

          {/* Crawl Stats Inline */}
          {(isCrawling || crawlStats.pages > 0) && (
            <div className="flex items-center gap-3 text-xs glass-panel px-3 py-1.5 rounded-lg border-[var(--color-accent)]/20 animate-fade-in whitespace-nowrap">
              {isCrawling && <span className="text-[var(--color-warning)] animate-pulse">●</span>}
              {!isCrawling && <span className="text-[var(--color-success)]">✓</span>}
              <span className="text-[var(--color-foreground)]">{crawlStats.pages} <span className="text-[var(--color-muted)]">Pages</span></span>
              <span className="text-[var(--color-foreground)]">{crawlStats.chunks} <span className="text-[var(--color-muted)]">Chunks</span></span>
              <span className="text-[var(--color-muted)] text-[10px] hidden md:inline max-w-[150px] truncate">{crawlStats.status}</span>
            </div>
          )}
        </div>
      </div>

      {/* Main Chat Interface */}
      <div className="flex-1 overflow-y-auto px-4 py-8 scroll-smooth relative">
        <div className="max-w-4xl mx-auto space-y-8">
          {messages.map((msg) => (
            <div key={msg.id} className={`flex ${msg.role === "user" ? "justify-end" : "justify-start"} animate-slide-up`}>
              <div className={`max-w-[85%] rounded-2xl px-5 py-4 shadow-md ${
                msg.role === "user" ? "accent-gradient text-white" :
                msg.role === "system" ? "glass-panel text-[var(--color-muted)] text-sm border-dashed" : "glass-panel-solid border-[var(--color-border-bright)]"
              }`}>
                
                {/* Embedded Pipeline Transparency */}
                {msg.role === "assistant" && msg.pipeline && msg.pipeline.length > 0 && (
                  <div className="mb-4 pb-3 border-b border-[var(--color-border)] space-y-1 bg-[#0a0a0f]/50 p-3 rounded-xl shadow-inner">
                    <p className="text-[10px] font-bold text-[var(--color-accent)] uppercase tracking-wider mb-2">Pipeline Execution Log</p>
                    {msg.pipeline.map((stage, i) => <StageIndicator key={i} stage={stage} />)}
                  </div>
                )}

                <div className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</div>
                
                {/* Response Sources */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-4 pt-3 border-t border-[var(--color-border)]">
                    <p className="text-[10px] uppercase font-semibold text-[var(--color-muted)] tracking-wider mb-2">Knowledge Matrix Sources</p>
                    <div className="flex flex-wrap gap-1.5">
                      {msg.sources.map((src, i) => (
                        <a key={i} href={src.startsWith('http') ? src : undefined} target="_blank" rel="noopener noreferrer" 
                           className="badge badge-info text-[10px] truncate max-w-[200px] hover:bg-[var(--color-accent)]/20 transition-colors" title={src}>
                          {src.replace(/^https?:\/\//, '')}
                        </a>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            </div>
          ))}

          {/* Active Generation State */}
          {isProcessing && liveStages.length > 0 && (
            <div className="flex justify-start animate-slide-up">
              <div className="max-w-[85%] rounded-2xl px-5 py-4 glass-panel border-[var(--color-accent)]/50 shadow-[0_0_15px_rgba(56,189,248,0.1)]">
                <div className="space-y-1">
                  <p className="text-[10px] font-bold text-[var(--color-warning)] uppercase tracking-wider mb-2 flex items-center gap-2">
                    <span className="w-1.5 h-1.5 rounded-full bg-[var(--color-warning)] animate-pulse shadow-[0_0_5px_var(--color-warning)]" />
                    Executing RAG Pipeline...
                  </p>
                  {liveStages.map((stage, i) => <StageIndicator key={i} stage={stage} />)}
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} className="h-4" />
        </div>
      </div>

      {/* Query Bar */}
      <div className="px-6 py-4 border-t border-[var(--color-border)] bg-[var(--color-surface)] shadow-[0_-5px_15px_rgba(0,0,0,0.2)] z-10">
        <div className="max-w-4xl mx-auto">
          <form onSubmit={e => { e.preventDefault(); handleSend(); }} className="flex gap-3 relative">
            <input 
              type="text" value={input} onChange={e => setInput(e.target.value)}
              placeholder="Ask anything about your ingested data..."
              className="input-dark flex-1 h-12 pr-24 focus:border-[var(--color-accent)] shadow-inner"
              disabled={isProcessing}
            />
            <button type="submit" disabled={!input.trim() || isProcessing} 
              className="absolute right-1.5 top-1.5 bottom-1.5 bg-gradient-to-r from-[var(--color-accent-gradient-from)] to-[var(--color-accent-gradient-to)] text-white font-bold px-5 rounded-[10px] text-sm hover:opacity-90 disabled:opacity-50 transition-all shadow-md">
              {isProcessing ? "Processing" : "Ask"}
            </button>
          </form>
          <div className="text-center mt-2.5 text-[10px] font-medium text-[var(--color-muted)] flex items-center justify-center gap-2">
            <span className="w-1 h-1 rounded-full bg-[var(--color-success)] hidden sm:block"></span>
            Powered by Llama 3.2, FAISS, and LangChain Edge
          </div>
        </div>
      </div>
    </div>
  );
}
