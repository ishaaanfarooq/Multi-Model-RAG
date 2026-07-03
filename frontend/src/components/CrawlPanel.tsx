"use client";

import { useState, useCallback, useEffect, useRef } from "react";
import { GlobeIcon, CheckIcon, WarningIcon, LinkIcon } from "@/components/icons";

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
      alert("Please provide a valid URL (including http:// or https://)");
      return;
    }

    setIsCrawling(true);
    setCurrentStatus({
      status: "initializing",
      pages_done: 0,
      total_found: 0,
      message: "Connecting to the target site…",
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
          message: "Crawl failed — could not reach the host.",
        },
      ]);
      eventSource.close();
    };
  }, [url, isCrawling]);

  return (
    <div className="flex flex-col h-full bg-cream-100 min-h-0">
      {/* Header */}
      <div className="px-10 py-10 bg-white border-b border-cream-300 z-10">
        <h2 className="text-2xl font-semibold tracking-tight text-ink font-heading">
          Web Sources
        </h2>
        <p className="text-xs font-medium text-stone-500 mt-1.5 uppercase tracking-widest opacity-70">
          Crawl a website and add its content to the knowledge base
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-12">
        <div className="max-w-4xl mx-auto space-y-12">

          {/* Target Module */}
          <div className="p-10 rounded-[40px] bg-white border border-cream-300 structural-card relative overflow-hidden group">
             <div className="absolute top-0 right-0 p-6 text-brass-900 opacity-[0.04] transition-opacity duration-500 group-hover:opacity-[0.07]">
                <GlobeIcon className="w-32 h-32 transition-transform duration-700 group-hover:scale-110" />
             </div>

             <div className="relative z-10 flex flex-col items-center">
                <label className="text-[10px] font-semibold text-brass-600 uppercase tracking-[0.2em] block mb-6 text-center">
                   Target URL
                </label>
                <div className="flex gap-4 w-full">
                   <div className="flex-1 relative">
                      <div className="absolute left-5 top-1/2 -translate-y-1/2 text-stone-400">
                        <LinkIcon className="w-[18px] h-[18px]" />
                      </div>
                      <input
                         type="url"
                         value={url}
                         onChange={(e) => setUrl(e.target.value)}
                         placeholder="Enter a URL (e.g., https://example.com)"
                         className="input-warm !pl-16 bg-cream-50 py-4"
                         disabled={isCrawling}
                      />
                   </div>
                   <button
                      onClick={handleCrawl}
                      disabled={!url.trim() || isCrawling}
                      className="btn-premium px-10 rounded-[20px] shadow-lg whitespace-nowrap min-w-[200px]"
                   >
                      {isCrawling ? "Crawling…" : "Start Crawl"}
                   </button>
                </div>
                <p className="mt-4 text-[10px] font-semibold text-stone-500 opacity-60 uppercase tracking-widest leading-relaxed text-center">
                   Supports single pages and site maps · up to 15 pages
                </p>
             </div>
          </div>

          {/* Active Status Module */}
          {currentStatus && (
            <div className="animate-structural-up p-8 rounded-[32px] border-2 border-brass-200/60 bg-white shadow-xl shadow-brass-900/5 relative overflow-hidden">
               {isCrawling && (
                 <div className="absolute top-0 left-0 w-full h-[3px] bg-gradient-to-r from-transparent via-brass-400 to-transparent animate-[shimmer_2s_infinite]" />
               )}
               <div className="flex items-start justify-between mb-8">
                  <div className="flex items-center gap-4">
                     <div className="w-14 h-14 rounded-2xl bg-brass-50 border border-brass-100 flex items-center justify-center text-brass-700 shadow-sm">
                        <GlobeIcon className="w-6 h-6" />
                     </div>
                     <div>
                        <h3 className="text-lg font-semibold text-ink font-heading">
                           {isCrawling ? "Crawl in progress" : "Crawl result"}
                        </h3>
                        <p className="text-xs font-semibold text-brass-600 uppercase tracking-widest opacity-90 mt-0.5">
                           Target: {url.replace(/^https?:\/\//, '')}
                        </p>
                     </div>
                  </div>
                  <div className="flex items-center gap-2 px-4 py-2 bg-cream-100 border border-cream-300 rounded-full text-[10px] font-semibold text-stone-600 tracking-widest uppercase">
                      {currentStatus.status}
                  </div>
               </div>

               <div className="grid grid-cols-2 gap-6 mb-8">
                  <div className="p-4 rounded-3xl bg-cream-100 border border-cream-300 flex flex-col items-center justify-center">
                     <span className="text-2xl font-semibold font-heading text-ink">{currentStatus.pages_done}</span>
                     <span className="text-[10px] font-semibold text-stone-500 uppercase tracking-widest mt-1 opacity-70">Pages scanned</span>
                  </div>
                  <div className="p-4 rounded-3xl bg-cream-100 border border-cream-300 flex flex-col items-center justify-center">
                      <span className="text-2xl font-semibold font-heading text-ink">{currentStatus.total_found}</span>
                      <span className="text-[10px] font-semibold text-stone-500 uppercase tracking-widest mt-1 opacity-70">Links found</span>
                  </div>
               </div>

               <div className="p-4 rounded-2xl bg-white border border-brass-100/60 italic text-sm text-ink">
                  &quot;{currentStatus.message}&quot;
               </div>

               {currentStatus.total_chunks && (
                  <div className="mt-4 p-4 rounded-2xl bg-sage-50 border border-sage-100 flex items-center justify-between">
                      <span className="text-xs font-semibold text-sage-700 uppercase tracking-widest flex items-center gap-2">
                        <CheckIcon className="w-4 h-4" /> Embedding complete
                      </span>
                      <span className="text-xs font-semibold text-sage-700 bg-white px-3 py-1 rounded-lg border border-sage-100">
                         {currentStatus.total_chunks} chunks added
                      </span>
                  </div>
               )}
            </div>
          )}

          {/* History Feed */}
          {history.length > 0 && (
            <div className="space-y-6 pt-10">
               <h3 className="text-xs font-semibold text-stone-500 uppercase tracking-[0.2em] border-b border-cream-300 pb-3">Previous crawls</h3>
               <div className="space-y-3">
                  {history.map((h, i) => (
                    <div key={i} className="p-4 rounded-2xl bg-white border border-cream-300 flex items-center justify-between opacity-80 hover:opacity-100 transition-opacity duration-300">
                       <div className="flex items-center gap-4">
                          <span className={h.status === 'error' ? 'text-brick-500' : 'text-sage-500'}>
                            {h.status === 'error' ? <WarningIcon className="w-5 h-5" /> : <CheckIcon className="w-5 h-5" />}
                          </span>
                          <div>
                             <p className="text-xs font-semibold text-ink">{h.pages_done} pages scanned</p>
                             <p className="text-[10px] font-medium text-stone-500 italic truncate max-w-[300px]">{h.message}</p>
                          </div>
                       </div>
                       <span className="text-[10px] font-semibold text-brass-700 uppercase p-2 py-1 bg-brass-50 rounded-lg">Log</span>
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
