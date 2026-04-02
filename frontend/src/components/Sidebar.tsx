"use client";

import { useEffect, useState } from "react";

type ViewType = "chat" | "upload" | "crawl" | "pipeline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
}

const navItems: { id: ViewType; label: string; icon: string; desc: string }[] = [
  { id: "chat", label: "Agentic Chat", icon: "✨", desc: "Interact with RAG" },
  { id: "upload", label: "Knowledge Ingest", icon: "📂", desc: "Process documents" },
  { id: "crawl", label: "Web Intelligence", icon: "🕸️", desc: "Structure websites" },
  { id: "pipeline", label: "Pipeline Watch", icon: "🔭", desc: "Monitor stages" },
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
    <aside className="w-[300px] h-screen flex flex-col bg-white border-r border-[#F1F1EF] transition-all duration-300">
      {/* Branding Section */}
      <div className="p-8 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-[#B45309] flex items-center justify-center text-white shadow-lg shadow-amber-900/10"> 
            <span className="font-bold text-xl">M</span>
          </div>
          <div>
            <h1 className="text-xl font-bold tracking-tight text-[#18181B] font-heading">
              MultiModel
            </h1>
            <p className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.2em] opacity-80">
              Agentic Framework
            </p>
          </div>
        </div>
      </div>

      {/* Navigation Layer */}
      <nav className="flex-1 px-4 py-8 space-y-2">
        <p className="px-4 text-[10px] font-bold text-[#71717A] uppercase tracking-[0.1em] mb-4">Pipeline Controls</p>
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`
                w-full flex items-center gap-4 px-4 py-3.5 rounded-2xl text-left transition-all duration-300 group
                ${
                  isActive
                    ? "bg-[#FAF9F6] border border-[#F1F1EF] shadow-sm text-[#18181B]"
                    : "border border-transparent text-[#71717A] hover:bg-[#FAF9F6] hover:text-[#18181B]"
                }
              `}
            >
              <div className={`
                w-10 h-10 rounded-xl flex items-center justify-center text-lg transition-all duration-300
                ${isActive ? "bg-white shadow-md scale-110" : "bg-transparent group-hover:bg-white group-hover:shadow-sm"}
              `}>
                {item.icon}
              </div>
              <div className="flex-1">
                <div className={`text-sm font-semibold transition-colors duration-300 ${isActive ? "text-[#B45309]" : ""}`}>
                  {item.label}
                </div>
                <div className="text-[10px] opacity-60 font-medium">{item.desc}</div>
              </div>
              {isActive && (
                <div className="w-1.5 h-1.5 rounded-full bg-[#B45309] shadow-[0_0_8px_#B45309]" />
              )}
            </button>
          );
        })}
      </nav>

      {/* System Integrity Module */}
      <div className="p-6">
        <div className="p-5 rounded-3xl bg-[#FAF9F6] border border-[#F1F1EF] structural-card">
          <p className="text-[10px] font-bold text-[#71717A] uppercase tracking-widest mb-3 opacity-60 text-center">System Integrity</p>
          <div className="flex flex-col gap-3">
             <div className="flex items-center justify-between px-2">
                <span className="text-[11px] font-semibold text-[#71717A]">Backend Status</span>
                <div className="flex items-center gap-2">
                  <span className={`w-1.5 h-1.5 rounded-full ${
                    backendStatus === "online" ? "bg-green-600 shadow-[0_0_8px_#16a34a]" : 
                    backendStatus === "checking" ? "bg-amber-500 animate-pulse" : "bg-red-600"
                  }`} />
                  <span className={`text-[11px] font-bold uppercase ${
                    backendStatus === "online" ? "text-green-700" : 
                    backendStatus === "checking" ? "text-amber-600" : "text-red-700"
                  }`}>
                    {backendStatus}
                  </span>
                </div>
             </div>
             <div className="h-px bg-[#E4E4E5] opacity-50" />
             <div className="flex items-center justify-between px-2">
                <span className="text-[11px] font-semibold text-[#71717A]">LLM Model</span>
                <span className="text-[11px] font-bold text-[#18181B]">Llama-3.2-4B</span>
             </div>
          </div>
        </div>
        <p className="text-center text-[10px] text-[#71717A] mt-4 opacity-40 font-medium">© 2026 MultiModel Framework</p>
      </div>
    </aside>
  );
}
