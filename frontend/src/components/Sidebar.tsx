"use client";

import { useEffect, useState } from "react";

type ViewType = "chat" | "upload" | "crawl" | "pipeline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const navItems: { id: ViewType; label: string; icon: string; desc: string }[] = [
  { id: "chat", label: "Chat", icon: "💬", desc: "Ask questions" },
  { id: "upload", label: "Upload", icon: "📄", desc: "Ingest documents" },
  { id: "crawl", label: "Crawl", icon: "🌐", desc: "Scrape websites" },
  { id: "pipeline", label: "Pipeline", icon: "⚡", desc: "Monitor stages" },
];

export default function Sidebar({ activeView, onViewChange }: SidebarProps) {
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");

  useEffect(() => {
    const checkHealth = async () => {
      try {
        const res = await fetch(`${API_BASE}/api/health`);
        setBackendStatus(res.ok ? "online" : "offline");
      } catch {
        setBackendStatus("offline");
      }
    };
    checkHealth();
    const interval = setInterval(checkHealth, 15000);
    return () => clearInterval(interval);
  }, []);

  return (
    <aside className="w-[260px] h-screen flex flex-col glass-panel-solid border-r border-[var(--color-border)] rounded-none">
      {/* Logo */}
      <div className="p-6 pb-2">
        <h1 className="text-lg font-bold tracking-tight accent-gradient-text">
          MultiModel RAG
        </h1>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          Cloud-Based AI Pipeline
        </p>
      </div>

      {/* Divider */}
      <div className="mx-5 my-3 h-px bg-[var(--color-border)]" />

      {/* Navigation */}
      <nav className="flex-1 px-3 space-y-1">
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`
                w-full flex items-center gap-3 px-4 py-3 rounded-xl text-left transition-all duration-200
                ${
                  isActive
                    ? "bg-[var(--color-surface-hover)] border border-[var(--color-border-bright)] glow-accent text-[var(--color-foreground)]"
                    : "border border-transparent text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-foreground)]"
                }
              `}
            >
              <span className="text-xl">{item.icon}</span>
              <div>
                <div className={`text-sm font-semibold ${isActive ? "accent-gradient-text" : ""}`}>
                  {item.label}
                </div>
                <div className="text-xs text-[var(--color-muted)]">{item.desc}</div>
              </div>
              {isActive && (
                <div className="ml-auto w-1.5 h-6 rounded-full accent-gradient" />
              )}
            </button>
          );
        })}
      </nav>

      {/* Bottom: System Status */}
      <div className="p-4 mx-3 mb-4 rounded-xl bg-[var(--color-background)] border border-[var(--color-border)]">
        <div className="flex items-center gap-2 text-xs">
          <div
            className={`w-2 h-2 rounded-full ${
              backendStatus === "online"
                ? "bg-[var(--color-success)] animate-pulse-glow"
                : backendStatus === "checking"
                ? "bg-[var(--color-warning)] animate-pulse"
                : "bg-[var(--color-error)]"
            }`}
          />
          <span className="text-[var(--color-muted)]">
            Backend:{" "}
            <span
              className={`font-semibold ${
                backendStatus === "online"
                  ? "text-[var(--color-success)]"
                  : backendStatus === "checking"
                  ? "text-[var(--color-warning)]"
                  : "text-[var(--color-error)]"
              }`}
            >
              {backendStatus === "online" ? "Online" : backendStatus === "checking" ? "Checking..." : "Offline"}
            </span>
          </span>
        </div>
        <p className="text-[10px] text-[var(--color-muted)] mt-1.5 opacity-60">
          FastAPI + Ollama + FAISS
        </p>
      </div>
    </aside>
  );
}
