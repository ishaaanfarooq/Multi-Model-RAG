"use client";

import { useEffect, useRef, useState } from "react";
import { ChatIcon, DocumentIcon, GlobeIcon, PulseIcon, CloseIcon, PanelLeftIcon } from "@/components/icons";
import type { Conversation } from "@/lib/conversations";
import ConfirmDialog from "@/components/ConfirmDialog";

export type ViewType = "chat" | "upload" | "crawl" | "pipeline";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface SidebarProps {
  activeView: ViewType;
  onViewChange: (view: ViewType) => void;
  conversations: Conversation[];
  activeConversationId: string | null;
  onNewChat: () => void;
  onOpenChat: (id: string) => void;
  onDeleteChat: (id: string) => void;
  onRenameChat: (id: string, title: string) => void;
  onCollapse: () => void;
}

const navItems: { id: ViewType; label: string; desc: string; Icon: typeof ChatIcon }[] = [
  { id: "chat", label: "Conversation", desc: "Ask questions, attach context", Icon: ChatIcon },
  { id: "upload", label: "Documents", desc: "Upload & index files", Icon: DocumentIcon },
  { id: "crawl", label: "Web Sources", desc: "Crawl & ingest a URL", Icon: GlobeIcon },
  { id: "pipeline", label: "Pipeline", desc: "Watch retrieval in real time", Icon: PulseIcon },
];

export default function Sidebar({
  activeView,
  onViewChange,
  conversations,
  activeConversationId,
  onNewChat,
  onOpenChat,
  onDeleteChat,
  onRenameChat,
  onCollapse,
}: SidebarProps) {
  const [backendStatus, setBackendStatus] = useState<"online" | "offline" | "checking">("checking");
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const [deleteTarget, setDeleteTarget] = useState<Conversation | null>(null);

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

  useEffect(() => {
    if (renamingId) renameInputRef.current?.focus();
  }, [renamingId]);

  const startRename = (c: Conversation) => {
    setRenamingId(c.id);
    setRenameDraft(c.title);
  };
  const commitRename = () => {
    if (renamingId) onRenameChat(renamingId, renameDraft);
    setRenamingId(null);
  };

  return (
    <aside className="w-[280px] h-screen flex flex-col bg-white border-r border-cream-300 flex-shrink-0">
      {/* Branding */}
      <div className="p-6 pb-3">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-2xl bg-brass-500 flex items-center justify-center text-white shadow-lg shadow-brass-900/10 flex-shrink-0">
            <span className="font-serif font-semibold text-xl">P</span>
          </div>
          <div className="min-w-0">
            <h1 className="text-xl font-semibold tracking-tight text-ink font-heading leading-tight">
              Praxis
            </h1>
            <p className="text-[10px] font-semibold text-brass-600 uppercase tracking-[0.14em] opacity-90 whitespace-nowrap">
              Agentic Workspace
            </p>
          </div>
          <button
            onClick={onCollapse}
            title="Collapse sidebar"
            aria-label="Collapse sidebar"
            className="ml-auto flex-shrink-0 w-8 h-8 flex items-center justify-center rounded-xl text-stone-400 hover:text-brass-600 hover:bg-cream-100 transition-colors"
          >
            <PanelLeftIcon className="w-[18px] h-[18px]" />
          </button>
        </div>
      </div>

      {/* New chat */}
      <div className="px-4 pt-1 pb-2">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-2xl bg-brass-500 text-white text-sm font-semibold shadow-sm hover:bg-brass-600 transition-colors"
        >
          <span className="text-lg leading-none -mt-0.5">＋</span>
          New chat
        </button>
      </div>

      {/* Navigation */}
      <nav className="px-4 py-2 space-y-1">
        <p className="px-4 text-[10px] font-semibold text-stone-500 uppercase tracking-[0.14em] mb-2">Workspace</p>
        {navItems.map((item) => {
          const isActive = activeView === item.id;
          const { Icon } = item;
          return (
            <button
              key={item.id}
              onClick={() => onViewChange(item.id)}
              className={`
                w-full flex items-center gap-3.5 px-4 py-2.5 rounded-2xl text-left transition-all duration-200 group
                ${
                  isActive
                    ? "bg-cream-100 border border-cream-300 text-ink"
                    : "border border-transparent text-stone-600 hover:bg-cream-50 hover:text-ink"
                }
              `}
            >
              <div className={`
                w-8 h-8 rounded-xl flex items-center justify-center transition-all duration-200 flex-shrink-0
                ${isActive ? "bg-brass-500 text-white shadow-sm" : "bg-cream-100 text-stone-500 group-hover:text-brass-600"}
              `}>
                <Icon className="w-[16px] h-[16px]" />
              </div>
              <div className="flex-1 min-w-0">
                <div className={`text-[13px] font-semibold transition-colors duration-200 ${isActive ? "text-ink" : ""}`}>
                  {item.label}
                </div>
              </div>
              {isActive && <div className="w-1.5 h-1.5 rounded-full bg-brass-500 flex-shrink-0" />}
            </button>
          );
        })}
      </nav>

      {/* Chat history */}
      <div className="flex-1 min-h-0 flex flex-col px-4 pt-3">
        <p className="px-4 text-[10px] font-semibold text-stone-500 uppercase tracking-[0.14em] mb-2 flex-shrink-0">
          Chat history
        </p>
        <div className="flex-1 overflow-y-auto space-y-0.5 pr-1">
          {conversations.length === 0 ? (
            <p className="px-4 py-2 text-[11px] text-stone-400 italic">No saved chats yet</p>
          ) : (
            conversations.map((c) => {
              const isActive = c.id === activeConversationId && activeView === "chat";
              const isRenaming = renamingId === c.id;
              return (
                <div
                  key={c.id}
                  className={`group flex items-center gap-1 rounded-xl transition-colors ${
                    isActive ? "bg-cream-100 border border-cream-300" : "border border-transparent hover:bg-cream-50"
                  }`}
                >
                  {isRenaming ? (
                    <input
                      ref={renameInputRef}
                      value={renameDraft}
                      onChange={(e) => setRenameDraft(e.target.value)}
                      onBlur={commitRename}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename();
                        if (e.key === "Escape") setRenamingId(null);
                      }}
                      className="flex-1 min-w-0 bg-white border border-brass-300 rounded-lg px-2.5 py-1.5 text-[13px] text-ink outline-none mx-1 my-0.5"
                    />
                  ) : (
                    <>
                      <button
                        onClick={() => onOpenChat(c.id)}
                        onDoubleClick={() => startRename(c)}
                        title={c.title}
                        className="flex-1 min-w-0 flex items-center gap-2.5 px-3 py-2 text-left"
                      >
                        <ChatIcon className={`w-3.5 h-3.5 flex-shrink-0 ${isActive ? "text-brass-600" : "text-stone-400"}`} />
                        <span className={`truncate text-[13px] font-medium ${isActive ? "text-ink" : "text-stone-600"}`}>
                          {c.title}
                        </span>
                      </button>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          setDeleteTarget(c);
                        }}
                        title="Delete chat"
                        className="opacity-0 group-hover:opacity-100 transition-opacity flex-shrink-0 w-7 h-7 flex items-center justify-center rounded-lg text-stone-400 hover:text-brick-600 hover:bg-brick-50 mr-1"
                      >
                        <CloseIcon className="w-3.5 h-3.5" />
                      </button>
                    </>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>

      {/* System Status */}
      <div className="p-4 pt-2 flex-shrink-0">
        <div className="p-3.5 rounded-2xl bg-cream-50 border border-cream-300">
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
      </div>

      <ConfirmDialog
        open={deleteTarget !== null}
        destructive
        title="Delete chat?"
        message={
          <>
            <span className="font-semibold text-ink">“{deleteTarget?.title}”</span> and its
            messages will be permanently removed. This can’t be undone.
          </>
        }
        confirmLabel="Delete"
        cancelLabel="Cancel"
        onConfirm={() => {
          if (deleteTarget) onDeleteChat(deleteTarget.id);
          setDeleteTarget(null);
        }}
        onCancel={() => setDeleteTarget(null)}
      />
    </aside>
  );
}
