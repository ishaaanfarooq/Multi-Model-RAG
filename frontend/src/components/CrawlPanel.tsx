"use client";

import { useState, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type CrawlEvent = {
  status: string;
  page_url: string;
  pages_done: number;
  total_found: number;
  message: string;
  total_chunks?: number;
};

export default function CrawlPanel() {
  const [url, setUrl] = useState("");
  const [maxPages, setMaxPages] = useState(20);
  const [maxDepth, setMaxDepth] = useState(2);
  const [isCrawling, setIsCrawling] = useState(false);
  const [events, setEvents] = useState<CrawlEvent[]>([]);
  const [summary, setSummary] = useState<CrawlEvent | null>(null);
  const [error, setError] = useState<string | null>(null);
  const logEndRef = useRef<HTMLDivElement>(null);

  const scrollLog = () => {
    logEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  const startCrawl = useCallback(() => {
    const trimmedUrl = url.trim();
    if (!trimmedUrl || isCrawling) return;

    // Basic URL validation
    try {
      new URL(trimmedUrl);
    } catch {
      setError("Please enter a valid URL (e.g., https://example.com)");
      return;
    }

    setError(null);
    setIsCrawling(true);
    setEvents([]);
    setSummary(null);

    const params = new URLSearchParams({
      url: trimmedUrl,
      max_pages: maxPages.toString(),
      max_depth: maxDepth.toString(),
    });

    const eventSource = new EventSource(`${API_BASE}/api/crawl/stream?${params}`);

    eventSource.onmessage = (event) => {
      try {
        const data: CrawlEvent = JSON.parse(event.data);
        setEvents((prev) => [...prev, data]);
        scrollLog();

        if (data.status === "completed" || data.status === "ingested") {
          setSummary(data);
        }
        if (data.status === "ingested" || data.status === "error") {
          setIsCrawling(false);
          eventSource.close();
        }
      } catch (err) {
        console.error("SSE parse error:", err);
      }
    };

    eventSource.onerror = () => {
      setError("Connection lost. Make sure the backend server is running.");
      setIsCrawling(false);
      eventSource.close();
    };
  }, [url, maxPages, maxDepth, isCrawling]);

  const getStatusIcon = (status: string) => {
    switch (status) {
      case "crawling":
        return "🔄";
      case "page_done":
        return "✅";
      case "page_skip":
        return "⏭️";
      case "page_error":
        return "❌";
      case "links_found":
        return "🔗";
      case "completed":
        return "🎉";
      case "ingested":
        return "💾";
      case "started":
        return "🚀";
      default:
        return "•";
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--color-border)]">
        <h2 className="text-xl font-bold tracking-tight">🌐 Crawl Website</h2>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          Scrape web pages and add their content to your knowledge base
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Config Panel */}
        <div className="glass-panel-solid p-6 space-y-5">
          {/* URL Input */}
          <div>
            <label className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider block mb-2">
              Website URL
            </label>
            <div className="flex gap-3">
              <input
                type="url"
                value={url}
                onChange={(e) => {
                  setUrl(e.target.value);
                  setError(null);
                }}
                placeholder="https://example.com"
                className="input-dark flex-1"
                disabled={isCrawling}
              />
              <button
                onClick={startCrawl}
                disabled={!url.trim() || isCrawling}
                className="btn-primary whitespace-nowrap"
              >
                {isCrawling ? "Crawling..." : "Start Crawl 🕷️"}
              </button>
            </div>
          </div>

          {/* Sliders */}
          <div className="grid grid-cols-2 gap-6">
            <div>
              <label className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider flex justify-between mb-2">
                <span>Max Pages</span>
                <span className="text-[var(--color-accent)]">{maxPages}</span>
              </label>
              <input
                type="range"
                min={1}
                max={50}
                value={maxPages}
                onChange={(e) => setMaxPages(Number(e.target.value))}
                disabled={isCrawling}
              />
            </div>
            <div>
              <label className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider flex justify-between mb-2">
                <span>Max Depth</span>
                <span className="text-[var(--color-accent)]">{maxDepth}</span>
              </label>
              <input
                type="range"
                min={1}
                max={5}
                value={maxDepth}
                onChange={(e) => setMaxDepth(Number(e.target.value))}
                disabled={isCrawling}
              />
            </div>
          </div>
        </div>

        {/* Error */}
        {error && (
          <div className="glass-panel p-4 border-[var(--color-error)] animate-slide-up">
            <div className="flex items-center gap-2">
              <span className="text-[var(--color-error)]">⚠️</span>
              <p className="text-sm text-[var(--color-error)]">{error}</p>
            </div>
          </div>
        )}

        {/* Summary */}
        {summary && (
          <div className="glass-panel-solid p-5 glow-success animate-slide-up">
            <h3 className="text-sm font-bold text-[var(--color-success)] mb-3 uppercase tracking-wider">
              Crawl Complete
            </h3>
            <div className="grid grid-cols-3 gap-4">
              <div className="text-center">
                <p className="text-2xl font-bold accent-gradient-text">{summary.pages_done}</p>
                <p className="text-xs text-[var(--color-muted)]">Pages Crawled</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold accent-gradient-text">{summary.total_chunks || 0}</p>
                <p className="text-xs text-[var(--color-muted)]">Chunks Indexed</p>
              </div>
              <div className="text-center">
                <p className="text-2xl font-bold accent-gradient-text">{summary.total_found}</p>
                <p className="text-xs text-[var(--color-muted)]">Links Found</p>
              </div>
            </div>
          </div>
        )}

        {/* Live Log */}
        {events.length > 0 && (
          <div>
            <h3 className="text-xs font-semibold text-[var(--color-muted)] uppercase tracking-wider mb-3">
              Crawl Log
            </h3>
            <div className="glass-panel-solid p-4 max-h-[300px] overflow-y-auto space-y-1.5">
              {events.map((ev, i) => (
                <div
                  key={i}
                  className="flex items-start gap-2 text-xs animate-fade-in"
                >
                  <span className="flex-shrink-0">{getStatusIcon(ev.status)}</span>
                  <span className="text-[var(--color-muted)] break-all">{ev.message}</span>
                </div>
              ))}
              <div ref={logEndRef} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
