"use client";

import { useEffect, useState } from "react";
import Sidebar, { ViewType } from "@/components/Sidebar";
import QueryPanel from "@/components/QueryPanel";
import IngestPanel from "@/components/IngestPanel";
import CrawlPanel from "@/components/CrawlPanel";
import PipelineVisualizer from "@/components/PipelineVisualizer";
import { useConversations } from "@/lib/conversations";
import { useTheme } from "@/lib/theme";
import { PanelLeftIcon } from "@/components/icons";
import VantaBackground from "@/components/VantaBackground";

const SIDEBAR_KEY = "mmrag.sidebarCollapsed";

export default function UnifiedPage() {
  const [activeView, setActiveView] = useState<ViewType>("chat");
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);
  const chats = useConversations();
  const { theme, toggle: toggleTheme } = useTheme();

  // Remember the collapsed state across reloads.
  useEffect(() => {
    if (typeof window !== "undefined" && localStorage.getItem(SIDEBAR_KEY) === "1") {
      setSidebarCollapsed(true);
    }
  }, []);

  const toggleSidebar = () =>
    setSidebarCollapsed((v) => {
      const next = !v;
      try {
        localStorage.setItem(SIDEBAR_KEY, next ? "1" : "0");
      } catch {
        /* ignore */
      }
      return next;
    });

  // Clicking a saved conversation (or New chat) also brings the chat view forward.
  const openChat = (id: string) => {
    chats.switchTo(id);
    setActiveView("chat");
  };
  const startNewChat = () => {
    chats.newChat();
    setActiveView("chat");
  };

  return (
    <div className="flex h-screen overflow-hidden bg-cream-100">
      {/* Animated collapse: the wrapper's width goes to 0 and clips the fixed-width
          sidebar, so its contents don't reflow during the transition. */}
      <div
        className={`flex-shrink-0 overflow-hidden transition-[width] duration-300 ease-in-out ${
          sidebarCollapsed ? "w-0" : "w-[280px]"
        }`}
      >
        <Sidebar
          activeView={activeView}
          onViewChange={setActiveView}
          conversations={chats.conversations}
          activeConversationId={chats.activeId}
          onNewChat={startNewChat}
          onOpenChat={openChat}
          onDeleteChat={chats.deleteChat}
          onRenameChat={chats.renameChat}
          onCollapse={toggleSidebar}
          theme={theme}
          onToggleTheme={toggleTheme}
        />
      </div>

      <main className="flex-1 flex flex-col h-screen overflow-hidden relative">
        {/* Floating expand button — only when the sidebar is hidden */}
        {sidebarCollapsed && (
          <button
            onClick={toggleSidebar}
            title="Open sidebar"
            aria-label="Open sidebar"
            className="absolute top-5 left-5 z-30 w-10 h-10 flex items-center justify-center rounded-2xl bg-white border border-cream-300 text-stone-500 hover:text-brass-600 shadow-sm hover:shadow-md transition-all"
          >
            <PanelLeftIcon className="w-[18px] h-[18px]" />
          </button>
        )}

        <VantaBackground theme={theme} />

        <div className="relative flex-1 flex flex-col min-h-0 p-6 lg:p-8 z-10">
          <div className="max-w-6xl mx-auto w-full flex-1 flex flex-col min-h-0 structural-card overflow-hidden">
            <div className="flex-1 flex flex-col min-h-0 overflow-hidden bg-white">
              {activeView === "chat" && (
                <QueryPanel
                  messages={chats.activeMessages}
                  setMessages={chats.setActiveMessages}
                  conversationId={chats.activeId}
                />
              )}
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
              <span>Praxis · Multi-Model Agentic RAG</span>
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
