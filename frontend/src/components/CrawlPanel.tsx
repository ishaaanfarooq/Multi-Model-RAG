"use client";

import { useState, useCallback, useEffect, useRef } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CrawlStatus = {
  status: string;
  pages_done: number;
  total_found: number;
  message: string;
  total_chunks?: number;
};

export default function CrawlPanel() {
  const [url, setUrl] = useState("");
  const [isCrawling, setIsCrawling] = useState(false);
  const [history, setHistory] = useState<CrawlStatus[]>([]);
  const [currentStatus, setCurrentStatus] = useState<CrawlStatus | null>(null);
  const statusEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    statusEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [currentStatus, history]);

  const handleCrawl = useCallback(() => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl || isCrawling) return;

    try {
      new URL(trimmedUrl);
    } catch {
      alert("Please provide a valid structural URL (including http:// or https://)");
      return;
    }

    setIsCrawling(true);
    setCurrentStatus({
      status: "initializing",
      pages_done: 0,
      total_found: 0,
      message: "Establishing connection to target host...",
    });

    const params = new URLSearchParams({
      url: trimmedUrl,
      max_pages: "15",
      max_depth: "2",
    });

    const eventSource = new EventSource(`${API_BASE}/api/crawl/stream?${params}`);

    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setCurrentStatus(data);

        if (data.status === "completed" || data.status === "ingested" || data.status === "error") {
          setIsCrawling(false);
          setHistory((prev) => [...prev, data]);
          eventSource.close();
        }
      } catch (err) {
        console.error("Crawl Stream Error:", err);
      }
    };

    eventSource.onerror = () => {
      setIsCrawling(false);
      setHistory((prev) => [
        ...prev,
        {
          status: "error",
          pages_done: 0,
          total_found: 0,
          message: "Crawl sequence aborted. Host connection failed.",
        },
      ]);
      eventSource.close();
    };
  }, [url, isCrawling]);

  return (
    <div className="flex flex-col h-full bg-[#FAF9F6]">
      {/* Structural Header */}
      <div className="px-10 py-10 bg-white border-b border-[#F1F1EF] z-10">
        <h2 className="text-2xl font-bold tracking-tight text-[#18181B] font-heading">
          Web Intelligence Ingress
        </h2>
        <p className="text-xs font-semibold text-[#71717A] mt-1.5 uppercase tracking-widest opacity-60">
          Deep-crawl and vectorize website content for structural knowledge
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-12">
        <div className="max-w-4xl mx-auto space-y-12">
          
          {/* Target Module */}
          <div className="p-10 rounded-[40px] bg-white border border-[#E4E4E5] structural-card relative overflow-hidden group">
             <div className="absolute top-0 right-0 p-6 opacity-[0.03] transition-opacity duration-500 group-hover:opacity-[0.06]">
                <span className="text-9xl transition-transform duration-700 group-hover:scale-110">🛰️</span>
             </div>
             
             <div className="relative z-10 flex flex-col items-center">
                <label className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.2em] block mb-6 text-center">
                   Target Intelligence Endpoint
                </label>
                <div className="flex gap-4 w-full">
                   <div className="flex-1 relative">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 text-zinc-400">🌐</div>
                      <input
                         type="url"
                         value={url}
                         onChange={(e) => setUrl(e.target.value)}
                         placeholder="Enter target URL (e.g., https://example.com)"
                         className="input-warm pl-12 bg-[#FCFBFA] py-4"
                         disabled={isCrawling}
                      />
                   </div>
                   <button
                      onClick={handleCrawl}
                      disabled={!url.trim() || isCrawling}
                      className="btn-premium px-10 rounded-[20px] shadow-lg whitespace-nowrap min-w-[200px]"
                   >
                      {isCrawling ? "Analyzing Host..." : "Initialize Crawl"}
                   </button>
                </div>
                <p className="mt-4 text-[10px] font-bold text-[#71717A] opacity-40 uppercase tracking-widest leading-relaxed text-center">
                   Verified Crawl Support: Single-page docs & full site mapping (max 15 pages)
                </p>
             </div>
          </div>

          {/* Active Status Module */}
          {currentStatus && (
            <div className="animate-structural-up p-8 rounded-[32px] border-2 border-amber-200/50 bg-white shadow-xl shadow-amber-900/5 relative overflow-hidden">
               {isCrawling && (
                 <div className="absolute top-0 left-0 w-full h-[3px] bg-gradient-to-r from-transparent via-amber-500 to-transparent animate-[shimmer_2s_infinite]" />
               )}
               <div className="flex items-start justify-between mb-8">
                  <div className="flex items-center gap-4">
                     <div className="w-14 h-14 rounded-2xl bg-amber-50 border border-amber-100 flex items-center justify-center text-2xl shadow-sm">
                        {isCrawling ? "🔎" : "🎯"}
                     </div>
                     <div>
                        <h3 className="text-lg font-bold text-[#18181B] font-heading">
                           {isCrawling ? "Intelligence Feed: Active" : "Intelligence Sequence Result"}
                        </h3>
                        <p className="text-xs font-bold text-[#B45309] uppercase tracking-widest opacity-80 mt-0.5">
                           Ingress Target: {url.replace(/^https?:\/\//, '')}
                        </p>
                     </div>
                  </div>
                  <div className="flex items-center gap-2 px-4 py-2 bg-zinc-50 border border-zinc-100 rounded-full text-[10px] font-bold text-zinc-700 tracking-widest uppercase">
                      {currentStatus.status}
                  </div>
               </div>

               <div className="grid grid-cols-2 gap-6 mb-8">
                  <div className="p-4 rounded-3xl bg-[#FAF9F6] border border-[#F1F1EF] flex flex-col items-center justify-center">
                     <span className="text-2xl font-bold font-heading text-[#18181B]">{currentStatus.pages_done}</span>
                     <span className="text-[10px] font-bold text-[#71717A] uppercase tracking-widest mt-1 opacity-60">Pages Scanned</span>
                  </div>
                  <div className="p-4 rounded-3xl bg-[#FAF9F6] border border-[#F1F1EF] flex flex-col items-center justify-center">
                      <span className="text-2xl font-bold font-heading text-[#18181B]">{currentStatus.total_found}</span>
                      <span className="text-[10px] font-bold text-[#71717A] uppercase tracking-widest mt-1 opacity-60">Verified Assets</span>
                  </div>
               </div>

               <div className="p-4 rounded-2xl bg-white border border-amber-100/50 italic text-sm text-zinc-900 flex gap-3 items-center">
                  <span className="text-xl">📻</span>
                  <p>&quot;{currentStatus.message}&quot;</p>
               </div>
               
               {currentStatus.total_chunks && (
                  <div className="mt-4 p-4 rounded-2xl bg-green-50 border border-green-100 flex items-center justify-between">
                      <span className="text-xs font-bold text-green-700 uppercase tracking-widest">Vector Embedding Complete</span>
                      <span className="text-xs font-bold text-green-900 bg-white px-3 py-1 rounded-lg border border-green-200">
                         {currentStatus.total_chunks} Neural Chunks Mapped
                      </span>
                  </div>
               )}
            </div>
          )}

          {/* History Feed */}
          {history.length > 0 && (
            <div className="space-y-6 pt-10">
               <h3 className="text-xs font-bold text-[#71717A] uppercase tracking-[0.2em] border-b border-zinc-200 pb-3">Previous Ingress Logs</h3>
               <div className="space-y-3">
                  {history.map((h, i) => (
                    <div key={i} className="p-4 rounded-2xl bg-white border border-[#F1F1EF] flex items-center justify-between opacity-70 hover:opacity-100 transition-opacity duration-300">
                       <div className="flex items-center gap-4">
                          <span className="text-xl">{h.status === 'error' ? '❌' : '✅'}</span>
                          <div>
                             <p className="text-xs font-bold text-zinc-900">Host Analysis: {h.pages_done} Pages</p>
                             <p className="text-[10px] font-medium text-zinc-500 italic truncate max-w-[300px]">{h.message}</p>
                          </div>
                       </div>
                       <span className="text-[10px] font-bold text-amber-700 uppercase p-2 py-1 bg-amber-50 rounded-lg">Historical Log</span>
                    </div>
                  ))}
               </div>
            </div>
          )}

          <div ref={statusEndRef} />
        </div>
      </div>
    </div>
  );
}
