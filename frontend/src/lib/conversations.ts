"use client";

import { useCallback, useEffect, useRef, useState } from "react";

// ─── Shared chat types (previously local to QueryPanel) ──────────────────────
export type PipelineStage = {
  model: string;
  status: string;
  action: string;
  details?: any;
};

export type PendingAction = {
  id: string;
  kind: "email" | "whatsapp";
  payload: {
    recipient_name: string;
    to: string;
    subject?: string;
    body: string;
  };
  status: string;
};

export type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  source_map?: Record<string, string>;
  chart?: string;
  warning?: string;
  timestamp: Date;
  pipeline?: PipelineStage[];
  images?: string[]; // base64 previews of uploaded images
  documents?: string[];
  urls?: string[];
  pendingAction?: PendingAction;
  actionOutcome?: { status: "sent" | "rejected" | "failed"; detail?: string };
};

export type Conversation = {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  updatedAt: number;
};

const STORAGE_KEY = "mmrag.conversations.v1";
const ACTIVE_KEY = "mmrag.activeConversation.v1";
const WELCOME =
  "Welcome. Upload a document, crawl a website, or attach an image to begin — then ask a question about it. Voice input is available too.";

const uid = () => `conv_${Date.now()}_${Math.random().toString(16).slice(2, 8)}`;

function welcomeMessage(): Message {
  return {
    id: "welcome",
    role: "system",
    content: WELCOME,
    timestamp: new Date(),
  };
}

function newConversation(): Conversation {
  const now = Date.now();
  return {
    id: uid(),
    title: "New chat",
    messages: [welcomeMessage()],
    createdAt: now,
    updatedAt: now,
  };
}

/** First real user message becomes the title, ChatGPT-style. */
function deriveTitle(messages: Message[]): string | null {
  const firstUser = messages.find((m) => m.role === "user");
  if (!firstUser) return null;
  const t = firstUser.content.trim().replace(/\s+/g, " ");
  if (!t) return null;
  return t.length > 40 ? t.slice(0, 40) + "…" : t;
}

// ── persistence ──────────────────────────────────────────────────────────────
function reviveTimestamps(convs: Conversation[]): Conversation[] {
  return convs.map((c) => ({
    ...c,
    messages: c.messages.map((m) => ({ ...m, timestamp: new Date(m.timestamp) })),
  }));
}

function load(): { conversations: Conversation[]; activeId: string | null } {
  if (typeof window === "undefined") return { conversations: [], activeId: null };
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    const activeId = localStorage.getItem(ACTIVE_KEY);
    if (!raw) return { conversations: [], activeId: null };
    const parsed = JSON.parse(raw) as Conversation[];
    return { conversations: reviveTimestamps(parsed), activeId };
  } catch {
    return { conversations: [], activeId: null };
  }
}

/**
 * Trim state that shouldn't (or can't) survive a reload before writing to
 * localStorage: base64 image previews are huge and blow the ~5MB quota, and a
 * pendingAction points at an in-memory server draft that won't exist after a
 * refresh — leaving it would render a dead Approve button.
 */
function forStorage(convs: Conversation[]): Conversation[] {
  return convs.map((c) => ({
    ...c,
    messages: c.messages.map(({ images, pendingAction, ...rest }) => rest),
  }));
}

function persist(conversations: Conversation[], activeId: string | null) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(forStorage(conversations)));
    if (activeId) localStorage.setItem(ACTIVE_KEY, activeId);
  } catch {
    // Quota exceeded even after stripping — drop the oldest conversations until it fits.
    try {
      const trimmed = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt).slice(0, 20);
      localStorage.setItem(STORAGE_KEY, JSON.stringify(forStorage(trimmed)));
    } catch {
      /* give up silently — persistence is best-effort */
    }
  }
}

// ── hook ──────────────────────────────────────────────────────────────────────
export function useConversations() {
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [activeId, setActiveId] = useState<string | null>(null);
  const [hydrated, setHydrated] = useState(false);

  // Load once on mount (client only, so SSR markup stays stable).
  useEffect(() => {
    const { conversations: loaded, activeId: savedActive } = load();
    if (loaded.length > 0) {
      setConversations(loaded);
      setActiveId(savedActive && loaded.some((c) => c.id === savedActive) ? savedActive : loaded[0].id);
    } else {
      const first = newConversation();
      setConversations([first]);
      setActiveId(first.id);
    }
    setHydrated(true);
  }, []);

  // Persist on change, but debounced — streaming appends a chunk per token, so an
  // immediate write would serialize the whole history hundreds of times per answer.
  const persistTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => {
    if (!hydrated) return;
    if (persistTimer.current) clearTimeout(persistTimer.current);
    persistTimer.current = setTimeout(() => persist(conversations, activeId), 400);
    return () => {
      if (persistTimer.current) clearTimeout(persistTimer.current);
    };
  }, [conversations, activeId, hydrated]);

  // Flush immediately if the tab is closing, so nothing in the debounce window is lost.
  useEffect(() => {
    if (!hydrated) return;
    const flush = () => persist(conversations, activeId);
    window.addEventListener("beforeunload", flush);
    return () => window.removeEventListener("beforeunload", flush);
  }, [conversations, activeId, hydrated]);

  const activeConversation = conversations.find((c) => c.id === activeId) || null;

  /** Replace the active conversation's messages; supports functional updates. */
  const setActiveMessages = useCallback(
    (updater: Message[] | ((prev: Message[]) => Message[])) => {
      setConversations((prev) =>
        prev.map((c) => {
          if (c.id !== activeId) return c;
          const nextMessages =
            typeof updater === "function" ? (updater as any)(c.messages) : updater;
          const derived = c.title === "New chat" ? deriveTitle(nextMessages) : null;
          return {
            ...c,
            messages: nextMessages,
            title: derived || c.title,
            updatedAt: Date.now(),
          };
        })
      );
    },
    [activeId]
  );

  const newChat = useCallback(() => {
    const conv = newConversation();
    setConversations((prev) => [conv, ...prev]);
    setActiveId(conv.id);
    return conv.id;
  }, []);

  const switchTo = useCallback((id: string) => setActiveId(id), []);

  const deleteChat = useCallback(
    (id: string) => {
      setConversations((prev) => {
        const remaining = prev.filter((c) => c.id !== id);
        if (remaining.length === 0) {
          const fresh = newConversation();
          setActiveId(fresh.id);
          return [fresh];
        }
        // If we deleted the active one, fall back to the most recent.
        setActiveId((curr) =>
          curr === id
            ? [...remaining].sort((a, b) => b.updatedAt - a.updatedAt)[0].id
            : curr
        );
        return remaining;
      });
    },
    []
  );

  const renameChat = useCallback((id: string, title: string) => {
    const clean = title.trim();
    if (!clean) return;
    setConversations((prev) => prev.map((c) => (c.id === id ? { ...c, title: clean } : c)));
  }, []);

  // Most-recent first for the sidebar list.
  const ordered = [...conversations].sort((a, b) => b.updatedAt - a.updatedAt);

  return {
    hydrated,
    conversations: ordered,
    activeId,
    activeConversation,
    activeMessages: activeConversation?.messages ?? [],
    setActiveMessages,
    newChat,
    switchTo,
    deleteChat,
    renameChat,
  };
}
