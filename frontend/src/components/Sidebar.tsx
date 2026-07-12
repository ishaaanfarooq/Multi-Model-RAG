"use client";

import { useEffect, useState } from "react";
import { ChatIcon, DocumentIcon, GlobeIcon, PulseIcon } from "@/components/icons";

export type ViewType = "chat" | "upload" | "crawl" | "pipeline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const navItems: { id: ViewType; label: string; desc: string; Icon: typeof ChatIcon }[] = [
  { id: "chat", label: "Conversation", desc: "Ask questions, attach context", Icon: ChatIcon },
  { id: "upload", label: "Documents", desc: "Upload & index files", Icon: DocumentIcon },
  { id: "crawl", label: "Web Sources", desc: "Crawl & ingest a URL", Icon: GlobeIcon },
  { id: "pipeline", label: "Pipeline", desc: "Watch retrieval in real time", Icon: PulseIcon },
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
    <aside className="w-[280px] h-screen flex flex-col bg-white border-r border-cream-300 flex-shrink-0">
      {/* Branding */}
      <div className="p-8 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brass-500 flex items-center justify-center text-white shadow-lg shadow-brass-900/10">
            <span className="font-serif font-semibold text-xl">M</span>
          </div>
          <div>
            <h1 className="text-lg font-semibold tracking-tight text-ink font-heading leading-tight">
              MultiModel RAG
            </h1>
            <p className="text-[10px] font-semibold text-brass-600 uppercase tracking-[0.18em] opacity-90">
              Research Workspace
            </p>
          </div>
        </div>
      </div>

      {/* Navigation */}
      <nav className="flex-1 px-4 py-6 space-y-1.5">
        <p className="px-4 text-[10px] font-semibold text-stone-500 uppercase tracking-[0.14em] mb-3">Workspace</p>
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          const { Icon } = item;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`
                w-full flex items-center gap-3.5 px-4 py-3 rounded-2xl text-left transition-all duration-200 group
                ${
                  isActive
                    ? "bg-cream-100 border border-cream-300 text-ink"
                    : "border border-transparent text-stone-600 hover:bg-cream-50 hover:text-ink"
                }
              `}
            >
              <div className={`
                w-9 h-9 rounded-xl flex items-center justify-center transition-all duration-200 flex-shrink-0
                ${isActive ? "bg-brass-500 text-white shadow-sm" : "bg-cream-100 text-stone-500 group-hover:text-brass-600"}
              `}>
                <Icon className="w-[18px] h-[18px]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className={`text-sm font-semibold transition-colors duration-200 ${isActive ? "text-ink" : ""}`}>
                  {item.label}
                </div>
                <div className="text-[11px] opacity-60 font-medium truncate">{item.desc}</div>
              </div>
              {isActive && <div className="w-1.5 h-1.5 rounded-full bg-brass-500 flex-shrink-0" />}
            </button>
          );
        })}
      </nav>

      {/* System Status */}
      <div className="p-6 pt-2">
        <div className="p-4 rounded-2xl bg-cream-50 border border-cream-300">
          <div className="flex flex-col gap-2.5">
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold text-stone-500">Backend</span>
              <div className="flex items-center gap-1.5">
                <span
                  className={`w-1.5 h-1.5 rounded-full ${
                    backendStatus === "online"
                      ? "bg-sage-500"
                      : backendStatus === "checking"
                      ? "bg-brass-400 animate-pulse"
                      : "bg-brick-500"
                  }`}
                />
                <span
                  className={`text-[11px] font-semibold ${
                    backendStatus === "online" ? "text-sage-700" : backendStatus === "checking" ? "text-brass-600" : "text-brick-700"
                  }`}
                >
                  {backendStatus === "online" ? "Online" : backendStatus === "checking" ? "Checking" : "Offline"}
                </span>
              </div>
            </div>
            <div className="h-px bg-cream-300" />
            <div className="flex items-center justify-between px-1">
              <span className="text-[11px] font-semibold text-stone-500">Model</span>
              <span className="text-[11px] font-semibold text-ink">Qwen2.5 3B</span>
            </div>
          </div>
        </div>
        <p className="text-center text-[10px] text-stone-500 mt-4 opacity-60 font-medium">© 2026 MultiModel RAG</p>
      </div>
    </aside>
  );
}
