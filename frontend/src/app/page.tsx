"use client";

import QueryPanel from "@/components/QueryPanel";

export default function UnifiedPage() {
  return (
    <div className="flex h-screen overflow-hidden bg-[#FAF9F6]">
      {/* Primary Workspace Area */}
      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        
        {/* Dynamic Background Texture/Atmosphere */}
        <div className="absolute inset-0 pointer-events-none opacity-20 bg-[radial-gradient(#B45309_1px,transparent_1px)] [background-size:24px_24px]" />
        <div className="absolute inset-0 pointer-events-none opacity-30 shadow-[inset_0_0_100px_rgba(250,249,246,1)]" />

        <div className="relative flex-1 flex flex-col min-h-0 p-8 z-10">
          <div className="max-w-6xl mx-auto w-full flex-1 flex flex-col min-h-0 structural-card overflow-hidden">
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white">
              <div className="flex-1 flex flex-col min-h-0">
                <QueryPanel />
              </div>
            </div>
          </div>
          
          {/* Subtle Workspace Footer */}
          <div className="max-w-6xl mx-auto w-full py-4 flex items-center justify-between px-2">
            <div className="flex items-center gap-4 text-[11px] font-semibold text-[#71717A] tracking-wide uppercase">
              <span className="flex items-center gap-2">
                 <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
                 Local Environment Ready
              </span>
              <span className="opacity-40">|</span>
              <span>Context: MultiModel RAG Framework</span>
            </div>
            <div className="flex items-center gap-2 text-[10px] text-[#71717A] italic opacity-60">
               Secured via Local LLM Ingress 🛡️
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
