"use client";

import { useState } from "react";
import Sidebar, { ViewType } from "@/components/Sidebar";
import QueryPanel from "@/components/QueryPanel";
import IngestPanel from "@/components/IngestPanel";
import CrawlPanel from "@/components/CrawlPanel";
import PipelineVisualizer from "@/components/PipelineVisualizer";

export default function UnifiedPage() {
  const [activeView, setActiveView] = useState<ViewType>("chat");

  return (
    <div className="flex h-screen overflow-hidden bg-cream-100">
      <Sidebar activeView={activeView} onViewChange={setActiveView} />

      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        <div className="absolute inset-0 pointer-events-none opacity-[0.4] bg-[radial-gradient(#D2C3A5_1px,transparent_1px)] [background-size:26px_26px]" />

        <div className="relative flex-1 flex flex-col min-h-0 p-6 lg:p-8 z-10">
          <div className="max-w-6xl mx-auto w-full flex-1 flex flex-col min-h-0 structural-card overflow-hidden">
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white">
              {activeView === "chat" && <QueryPanel />}
              {activeView === "upload" && <IngestPanel />}
              {activeView === "crawl" && <CrawlPanel />}
              {activeView === "pipeline" && <PipelineVisualizer />}
            </div>
          </div>

          <div className="max-w-6xl mx-auto w-full py-4 flex items-center justify-between px-2">
            <div className="flex items-center gap-4 text-[11px] font-semibold text-stone-500 tracking-wide uppercase">
              <span className="flex items-center gap-2">
                <span className="w-1.5 h-1.5 rounded-full bg-sage-500" />
                Local Environment Ready
              </span>
              <span className="opacity-40">|</span>
              <span>MultiModel RAG Framework</span>
            </div>
            <div className="text-[10px] text-stone-500 italic opacity-60">
              Runs entirely on your local infrastructure
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
