"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import ImageViewer from "@/components/ImageViewer";
import { DocumentIcon, GlobeIcon, ImageIcon, MicIcon, SendIcon, CloseIcon, WarningIcon, CheckIcon, ChatIcon, StopIcon } from "@/components/icons";
import type { Message, PipelineStage } from "@/lib/conversations";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type SetMessages = (updater: Message[] | ((prev: Message[]) => Message[])) => void;

interface QueryPanelProps {
  // Chat state is owned by the conversation store in the parent so it can be
  // persisted and switched between conversations.
  messages: Message[];
  setMessages: SetMessages;
  conversationId: string | null;
}

// Moving StageDisplay outside the component to prevent re-creation on every render
const StageDisplay = ({ stages }: { stages: PipelineStage[] }) => (
  <div className="flex flex-col gap-2 p-4 bg-cream-100 border border-cream-300 rounded-3xl mt-4 max-w-[500px]">
    <p className="text-[10px] font-semibold text-brass-600 uppercase tracking-[0.1em] mb-2 opacity-90">Pipeline Path</p>
    {stages.map((stage, i) => (
      <div key={i} className="flex items-center gap-3 text-[11px] font-medium text-stone-500">
        <span className={`w-1.5 h-1.5 rounded-full ${
          stage.status === 'Processing' ? 'bg-brass-400 animate-pulse' :
          stage.status === 'Completed' ? 'bg-sage-500' : 'bg-cream-300'
        }`} />
        <span className="text-ink font-semibold min-w-[140px] text-xs">{stage.model}</span>
        <span className="truncate opacity-70 italic">{stage.action}</span>
      </div>
    ))}
  </div>
);

export default function QueryPanel({ messages, setMessages, conversationId }: QueryPanelProps) {
  const [hasMounted, setHasMounted] = useState(false);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveStages, setLiveStages] = useState<PipelineStage[]>([]);
  const [modelChoice, setModelChoice] = useState<"local" | "api" | "claude">("local");

  // Voice input state
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Image upload state
  const [selectedImages, setSelectedImages] = useState<File[]>([]);
  const [imagePreviews, setImagePreviews] = useState<string[]>([]);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // Document and URL ingestion state
  const [selectedDocuments, setSelectedDocuments] = useState<File[]>([]);
  const [attachedUrls, setAttachedUrls] = useState<string[]>([]);
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [urlDraft, setUrlDraft] = useState("");
  const documentInputRef = useRef<HTMLInputElement>(null);

  // Viewport/ImageViewer state
  const [viewerImage, setViewerImage] = useState<{ src: string, alt: string } | null>(null);

  // id of the draft currently being sent/discarded, so we can disable its buttons
  const [resolvingAction, setResolvingAction] = useState<string | null>(null);

  // Handles to the in-flight stream so Stop can actually cut the connection. Closing
  // the stream also signals the backend to stop — its SSE generator bails out when it
  // sees request.is_disconnected().
  const eventSourceRef = useRef<EventSource | null>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const stoppedRef = useRef(false);

  useEffect(() => {
    setHasMounted(true);
  }, []);

  // Switching conversations: stop any in-flight stream and clear transient UI so a
  // new/other chat doesn't inherit the previous one's processing state or attachments.
  useEffect(() => {
    eventSourceRef.current?.close();
    eventSourceRef.current = null;
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;
    stoppedRef.current = true;
    setIsProcessing(false);
    setLiveStages([]);
    setInput("");
    clearImage();
    clearDocument();
    clearUrlAttachment();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [conversationId]);

  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLTextAreaElement>(null);

  // Use a ref for liveStages to capture them in the SSE callback without re-creating handleSend
  const stagesRef = useRef<PipelineStage[]>([]);

  useEffect(() => {
    stagesRef.current = liveStages;
  }, [liveStages]);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  };

  useEffect(scrollToBottom, [messages, liveStages]);

  // ─── Voice Input Logic ───────────────────────────────────────────
  const toggleVoiceInput = useCallback(() => {
    if (!('webkitSpeechRecognition' in window) && !('SpeechRecognition' in window)) {
      alert("Voice input is not supported in this browser. Please use Chrome.");
      return;
    }

    if (isListening) {
      recognitionRef.current?.stop();
      setIsListening(false);
      return;
    }

    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = true;
    recognition.lang = "en-US";

    recognition.onresult = (event: any) => {
      let transcript = "";
      for (let i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      setInput(transcript);
    };

    recognition.onend = () => {
      setIsListening(false);
    };

    recognition.onerror = (event: any) => {
      console.error("Speech recognition error:", event.error);
      setIsListening(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
    setIsListening(true);
  }, [isListening]);

  const appendSystemMessage = useCallback((content: string) => {
    setMessages((prev) => [...prev, {
      id: `${Date.now()}-${Math.random().toString(16).slice(2)}`,
      role: "system",
      content,
      timestamp: new Date(),
    }]);
  }, [setMessages]);

  // ─── Stop an in-flight request ───────────────────────────────────────
  const stopProcessing = useCallback(() => {
    stoppedRef.current = true;

    // Text stream (GET/EventSource)
    eventSourceRef.current?.close();
    eventSourceRef.current = null;

    // Image stream (POST/fetch) — abort cancels the reader loop
    abortControllerRef.current?.abort();
    abortControllerRef.current = null;

    // Keep whatever partial answer had streamed, but stop treating it as live.
    setMessages((prev) =>
      prev.map((m) =>
        m.id === "streaming-ai-msg" ? { ...m, id: `stopped-${Date.now()}` } : m
      )
    );
    setIsProcessing(false);
    setLiveStages([]);
    appendSystemMessage("Stopped.");
  }, [appendSystemMessage, setMessages]);

  // ─── Attachment Logic ────────────────────────────────────────────
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setSelectedImages(prev => [...prev, ...files]);
      files.forEach(file => {
        const reader = new FileReader();
        reader.onloadend = () => {
          setImagePreviews(prev => [...prev, reader.result as string]);
        };
        reader.readAsDataURL(file);
      });
    }
  };

  const handleDocumentSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files || []);
    if (files.length > 0) {
      setSelectedDocuments((prev) => [...prev, ...files]);
    }
  };

  const clearImage = (index?: number) => {
    if (index !== undefined) {
      setSelectedImages(prev => prev.filter((_, i) => i !== index));
      setImagePreviews(prev => prev.filter((_, i) => i !== index));
    } else {
      setSelectedImages([]);
      setImagePreviews([]);
      if (imageInputRef.current) {
        imageInputRef.current.value = "";
      }
    }
  };

  const clearDocument = (index?: number) => {
    if (index !== undefined) {
      setSelectedDocuments((prev) => prev.filter((_, i) => i !== index));
    } else {
      setSelectedDocuments([]);
      if (documentInputRef.current) {
        documentInputRef.current.value = "";
      }
    }
  };

  const addUrlAttachment = () => {
    const trimmed = urlDraft.trim();
    if (!trimmed) return;

    try {
      new URL(trimmed);
      setAttachedUrls((prev) => prev.includes(trimmed) ? prev : [...prev, trimmed]);
      setUrlDraft("");
      setShowUrlInput(false);
    } catch {
      appendSystemMessage("Please enter a valid URL including http:// or https://.");
    }
  };

  const clearUrlAttachment = (index?: number) => {
    if (index !== undefined) {
      setAttachedUrls((prev) => prev.filter((_, i) => i !== index));
    } else {
      setAttachedUrls([]);
    }
  };

  // ─── Approve / reject a drafted action ───────────────────────────────
  // The send happens here and only here, behind an explicit click. The model can
  // draft, but a human commits.
  const resolveAction = useCallback(async (messageId: string, actionId: string, approve: boolean) => {
    setResolvingAction(actionId);
    try {
      const res = await fetch(`${API_BASE}/api/actions/${actionId}/${approve ? "approve" : "reject"}`, {
        method: "POST",
      });
      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        throw new Error(data.detail || `Request failed (${res.status})`);
      }

      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                pendingAction: undefined,
                actionOutcome: {
                  status: approve ? "sent" : "rejected",
                  detail: approve ? "Sent successfully." : "Discarded — nothing was sent.",
                },
              }
            : m
        )
      );
    } catch (err) {
      setMessages((prev) =>
        prev.map((m) =>
          m.id === messageId
            ? {
                ...m,
                pendingAction: undefined,
                actionOutcome: {
                  status: "failed",
                  detail: err instanceof Error ? err.message : "Failed to send.",
                },
              }
            : m
        )
      );
    } finally {
      setResolvingAction(null);
    }
  }, [setMessages]);

  const formatHistory = () => {
    return messages
      .filter(m => m.role !== 'system')
      .slice(-6) // Include last 3 turns
      .map(m => `${m.role === 'user' ? 'User' : 'Assistant'}: ${m.content}`)
      .join('\n');
  };

  const ingestDocument = async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);

    const response = await fetch(`${API_BASE}/api/ingest`, {
      method: "POST",
      body: formData,
    });

    if (!response.ok) {
      throw new Error(`Failed to ingest ${file.name}`);
    }

    return response.json();
  };

  const crawlUrl = async (url: string) => {
    const response = await fetch(`${API_BASE}/api/crawl`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, max_pages: 15, max_depth: 2 }),
    });

    if (!response.ok) {
      throw new Error(`Failed to crawl ${url}`);
    }

    return response.json();
  };

  // ─── Send Logic (supports text, documents, URLs, and images) ─────
  const handleSend = useCallback(async () => {
    const query = input.trim();
    const hasImages = selectedImages.length > 0;
    const hasKnowledgeAttachments = selectedDocuments.length > 0 || attachedUrls.length > 0;
    if ((!query && !hasImages && !hasKnowledgeAttachments) || isProcessing) return;

    stoppedRef.current = false;
    const imageFiles = [...selectedImages];
    const imagePreviewSnapshot = [...imagePreviews];
    const documentFiles = [...selectedDocuments];
    const urlSnapshot = [...attachedUrls];
    const effectiveQuery = query || (hasImages ? "Describe the attached image." : "");

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: query || "Added knowledge sources to the workspace.",
      timestamp: new Date(),
      images: imagePreviewSnapshot.length > 0 ? imagePreviewSnapshot : undefined,
      documents: documentFiles.length > 0 ? documentFiles.map((file) => file.name) : undefined,
      urls: urlSnapshot.length > 0 ? urlSnapshot : undefined,
    };

    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    if (inputRef.current) {
      inputRef.current.style.height = 'auto';
    }
    setIsProcessing(true);
    setLiveStages([]);
    clearImage();
    clearDocument();
    clearUrlAttachment();

    try {
      for (const file of documentFiles) {
        setLiveStages((prev) => [...prev, {
          model: "Document Ingestion",
          status: "Processing",
          action: `Indexing ${file.name}`,
        }]);
        const result = await ingestDocument(file);
        setLiveStages((prev) => prev.map((stage) =>
          stage.model === "Document Ingestion"
            ? { ...stage, status: "Completed", action: `Ingested ${result.chunks} chunks from ${file.name}` }
            : stage
        ));
        appendSystemMessage(`Document ingested: ${file.name} (${result.chunks} chunks).`);
      }

      for (const url of urlSnapshot) {
        setLiveStages((prev) => [...prev, {
          model: "URL Crawler",
          status: "Processing",
          action: `Crawling ${url}`,
        }]);
        const result = await crawlUrl(url);
        setLiveStages((prev) => prev.map((stage) =>
          stage.model === "URL Crawler"
            ? { ...stage, status: "Completed", action: `Crawled ${result.pages_crawled} pages into ${result.total_chunks} chunks` }
            : stage
        ));
        appendSystemMessage(`URL crawled: ${url} (${result.total_chunks} chunks).`);
      }
    } catch (err) {
      appendSystemMessage(err instanceof Error ? err.message : "Knowledge ingestion failed.");
      setIsProcessing(false);
      setLiveStages([]);
      return;
    }

    if (!effectiveQuery) {
      appendSystemMessage("Knowledge sources are ready. Ask a question about the uploaded or crawled content.");
      setIsProcessing(false);
      setLiveStages([]);
      return;
    }

    // If we have images, use POST with FormData
    if (imageFiles.length > 0) {
      const formData = new FormData();
      formData.append("query", effectiveQuery);
      formData.append("history", formatHistory());
      formData.append("model_choice", modelChoice);
      imageFiles.forEach((file) => {
        formData.append("images", file);
      });

      // For POST+SSE we need to use fetch + ReadableStream
      const controller = new AbortController();
      abortControllerRef.current = controller;
      fetch(`${API_BASE}/api/stream`, {
        method: "POST",
        body: formData,
        signal: controller.signal,
      }).then(async (response) => {
        const reader = response.body?.getReader();
        const decoder = new TextDecoder();

        if (!reader) return;

        let buffer = "";
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;

          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (line.startsWith("data: ")) {
              try {
                const data = JSON.parse(line.slice(6));
                handleSSEData(data);
              } catch (err) {
                // skip malformed lines
              }
            }
          }
        }
        abortControllerRef.current = null;
      }).catch((err) => {
        // A user-initiated Stop aborts the fetch — that's expected, not an error.
        if (err?.name === "AbortError" || stoppedRef.current) return;
        setMessages((prev) => [...prev, {
          id: (Date.now() + 2).toString(),
          role: "system",
          content: "Failed to process image. Ensure the backend is running on port 8000.",
          timestamp: new Date(),
        }]);
        setIsProcessing(false);
        setLiveStages([]);
      });
    } else {
      // Text-only: use EventSource (GET)
      const eventSource = new EventSource(
        `${API_BASE}/api/stream?query=${encodeURIComponent(effectiveQuery)}&history=${encodeURIComponent(formatHistory())}&model_choice=${encodeURIComponent(modelChoice)}`
      );
      eventSourceRef.current = eventSource;

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const isFinal = handleSSEData(data);
          if (isFinal) {
            eventSource.close();
            eventSourceRef.current = null;
          }
        } catch (err) {
          console.error("Critical SSE parse error:", err);
        }
      };

      eventSource.onerror = () => {
        eventSource.close();
        eventSourceRef.current = null;
        // If the user pressed Stop, we closed the stream on purpose — stay quiet.
        if (stoppedRef.current) return;
        const errorMsg: Message = {
          id: (Date.now() + 2).toString(),
          role: "system",
          content: "Lost connection to the backend. Ensure the local server is running on port 8000.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
        setIsProcessing(false);
        setLiveStages([]);
      };
    }
  }, [input, isProcessing, selectedImages, imagePreviews, selectedDocuments, attachedUrls, modelChoice, messages, appendSystemMessage, setMessages]);

  // Shared SSE data handler — returns true if the stream is finished (final or failed)
  const handleSSEData = (data: any): boolean => {
    // Backend surfaced a real error (e.g. an API key is not configured).
    // Show its message instead of letting the closing stream fall through to
    // the generic "lost connection" handler.
    if (data.status === "Failed") {
      setMessages((prev) => [
        ...prev.filter((m) => m.id !== "streaming-ai-msg"),
        {
          id: `err-${Date.now()}`,
          role: "system",
          content: data.action || "The request failed.",
          timestamp: new Date(),
        },
      ]);
      setIsProcessing(false);
      setLiveStages([]);
      return true;
    }

    if (data.model === "Final Response" && data.status === "Processing" && data.action === "Streaming") {
      setMessages((prev) => {
        const idx = prev.findIndex(m => m.id === "streaming-ai-msg");
        const chunk = data.details?.answer_chunk || "";

        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = {
            ...updated[idx],
            content: updated[idx].content + chunk
          };
          return updated;
        } else {
          const streamingMsg: Message = {
            id: "streaming-ai-msg",
            role: "assistant",
            content: chunk,
            timestamp: new Date(),
            pipeline: [...stagesRef.current]
          };
          return [...prev, streamingMsg];
        }
      });
      return false;
    }

    if (data.model === "Final Response" && data.status === "Completed") {
      setMessages((prev) => {
        const filtered = prev.filter(m => m.id !== "streaming-ai-msg");
        const aiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.details?.answer || "No answer could be produced for this query.",
          sources: data.details?.sources || [],
          source_map: data.details?.source_map || undefined,
          chart: data.details?.chart || undefined,
          warning: data.details?.warning || undefined,
          pendingAction: data.details?.pending_action || undefined,
          timestamp: new Date(),
          pipeline: [...stagesRef.current, data].map(stage =>
            stage.model === data.model ? data : stage
          ),
        };
        return [...filtered, aiMsg];
      });

      setIsProcessing(false);
      setLiveStages([]);
      return true;
    } else {
      // Update live stages
      setLiveStages((prev) => {
        const idx = prev.findIndex((s) => s.model === data.model);
        if (idx >= 0) {
          const updated = [...prev];
          updated[idx] = data;
          return updated;
        }
        return [...prev, data];
      });
      return false;
    }
  };

  // ─── Citation-aware Markdown rendering ────────────────────────────
  const renderCitedContent = (content: string, sourceMap?: Record<string, string>) => {
    // Custom components for ReactMarkdown to handle citation links
    const components: any = {
      // Override paragraph rendering to handle [1], [2] citations
      p: ({ children, ...props }: any) => {
        return <p {...props}>{processCitations(children, sourceMap)}</p>;
      },
      li: ({ children, ...props }: any) => {
        return <li {...props}>{processCitations(children, sourceMap)}</li>;
      },
      td: ({ children, ...props }: any) => {
        return <td {...props}>{processCitations(children, sourceMap)}</td>;
      },
    };

    return (
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {content}
      </ReactMarkdown>
    );
  };

  // Process citation markers [1], [2] etc. into clickable superscripts
  const processCitations = (children: any, sourceMap?: Record<string, string>): any => {
    if (!sourceMap || !children) return children;

    return Array.isArray(children)
      ? children.map((child, i) => processSingleChild(child, sourceMap, i))
      : processSingleChild(children, sourceMap, 0);
  };

  const processSingleChild = (child: any, sourceMap: Record<string, string>, key: number): any => {
    if (typeof child !== "string") return child;

    const parts: any[] = [];
    const regex = /\[(\d+)\]/g;
    let lastIndex = 0;
    let match;

    while ((match = regex.exec(child)) !== null) {
      // Add text before the citation
      if (match.index > lastIndex) {
        parts.push(child.slice(lastIndex, match.index));
      }

      const citNum = match[1];
      const url = sourceMap[citNum];
      if (url) {
        parts.push(
          <a
            key={`cite-${key}-${citNum}-${match.index}`}
            href={url}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-brass-100 text-brass-800 text-[9px] font-bold no-underline hover:bg-brass-200 transition-colors align-super ml-0.5 mr-0.5 cursor-pointer"
            title={`Source ${citNum}: ${url}`}
          >
            {citNum}
          </a>
        );
      } else {
        parts.push(`[${citNum}]`);
      }
      lastIndex = regex.lastIndex;
    }

    // Add remaining text
    if (lastIndex < child.length) {
      parts.push(child.slice(lastIndex));
    }

    return parts.length > 0 ? parts : child;
  };

  return (
    <div className="flex flex-col h-full bg-white relative min-h-0">
      {/* Header */}
      <div className="px-10 py-8 border-b border-cream-300 bg-white z-10 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-ink font-heading">
            Conversation
          </h2>
          <p className="text-xs font-medium text-stone-500 mt-1.5 uppercase tracking-wide opacity-70">
            Ask questions across your documents, web sources, and images
          </p>
        </div>
        <div className="flex items-center gap-4">
           <label className="flex items-center gap-2 px-3 py-2 rounded-2xl bg-cream-100 border border-cream-300 text-[11px] font-semibold text-stone-500 uppercase tracking-wide">
             Model
             <select
               value={modelChoice}
               onChange={(e) => setModelChoice(e.target.value as "local" | "api" | "claude")}
               disabled={isProcessing}
               className="bg-white border border-cream-300 rounded-xl px-3 py-1.5 text-ink outline-none normal-case tracking-normal"
             >
               <option value="local">Local Qwen2.5 3B</option>
               <option value="api">API Gemini 2.0</option>
               <option value="claude">Claude Opus 4.8</option>
             </select>
           </label>
           {isProcessing && (
              <div className="flex items-center gap-2 group relative">
                <div className="flex items-center gap-2 px-3 py-1.5 bg-brass-50 border border-brass-100 rounded-full text-[11px] font-semibold text-brass-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-brass-500 animate-ping" />
                  Processing
                </div>
                <button
                  onClick={stopProcessing}
                  className="hidden group-hover:block absolute right-0 top-full mt-2 px-2 py-1 bg-brick-50 text-brick-700 text-[9px] font-bold rounded border border-brick-100 whitespace-nowrap shadow-sm z-50"
                >
                  Stop
                </button>
              </div>
           )}
        </div>
      </div>

      {/* Message Feed */}
      <div className="flex-1 overflow-y-auto px-10 py-10 space-y-8">
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex flex-col ${msg.role === "user" ? "items-end" : "items-start"} animate-structural-up`}
          >
            <div
              className={`max-w-[800px] ${
                msg.role === "user" ? "bubble-user" :
                msg.role === "system" ? "text-center mx-auto text-[11px] text-stone-500 italic opacity-70 py-4 max-w-[420px]" :
                "bubble-ai"
              }`}
            >
              <div className="relative">
                {msg.role === "assistant" && msg.pipeline && (
                  <StageDisplay stages={msg.pipeline} />
                )}

                {/* User document and URL previews */}
                {msg.role === "user" && ((msg.documents && msg.documents.length > 0) || (msg.urls && msg.urls.length > 0)) && (
                  <div className="flex flex-col gap-2 mb-3">
                    {msg.documents?.map((doc, idx) => (
                      <div key={`doc-${idx}`} className="flex items-center gap-2 rounded-xl bg-white/15 border border-white/20 px-3 py-2 text-xs font-semibold">
                        <DocumentIcon className="w-3.5 h-3.5" />
                        <span className="truncate max-w-[260px]">{doc}</span>
                      </div>
                    ))}
                    {msg.urls?.map((url, idx) => (
                      <div key={`url-${idx}`} className="flex items-center gap-2 rounded-xl bg-white/15 border border-white/20 px-3 py-2 text-xs font-semibold">
                        <GlobeIcon className="w-3.5 h-3.5" />
                        <span className="truncate max-w-[320px]">{url.replace(/^https?:\/\//, "")}</span>
                      </div>
                    ))}
                  </div>
                )}

                {/* User images preview */}
                {msg.role === "user" && msg.images && msg.images.length > 0 && (
                  <div className="flex flex-wrap gap-2 mb-3">
                    {msg.images.map((imgSrc, idx) => (
                      <div
                        key={idx}
                        className="rounded-xl overflow-hidden border border-white/20 max-w-[150px] cursor-pointer group/img relative"
                        onClick={() => setViewerImage({ src: imgSrc, alt: `Uploaded image ${idx + 1}` })}
                      >
                        <img src={imgSrc} alt="Uploaded" className="w-full h-auto group-hover:scale-105 transition-transform duration-500" />
                        <div className="absolute inset-0 bg-black/20 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                           <span className="text-white text-[10px] font-bold uppercase tracking-widest bg-black/40 px-2 py-1 rounded-full backdrop-blur-sm">View full size</span>
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                <div className={`text-[15px] leading-[1.65] font-medium ${msg.role === "assistant" ? "mt-4 text-ink-light prose prose-zinc max-w-none prose-sm prose-headings:mb-2 prose-p:mb-2 prose-table:border prose-table:border-cream-300 prose-th:bg-cream-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2" : ""}`}>
                  {msg.role === "assistant" ? (
                    renderCitedContent(msg.content, msg.source_map)
                  ) : (
                    msg.content
                  )}
                </div>

                {/* Drafted action awaiting approval — the human-in-the-loop gate */}
                {msg.pendingAction && (
                  <div className="mt-5 rounded-2xl border-2 border-brass-300 bg-brass-50/60 overflow-hidden">
                    <div className="flex items-center gap-2 px-5 py-3 bg-brass-100/70 border-b border-brass-200">
                      {msg.pendingAction.kind === "email" ? (
                        <DocumentIcon className="w-4 h-4 text-brass-700" />
                      ) : (
                        <ChatIcon className="w-4 h-4 text-brass-700" />
                      )}
                      <span className="text-[11px] font-semibold uppercase tracking-widest text-brass-800">
                        {msg.pendingAction.kind === "email" ? "Draft email" : "Draft WhatsApp"} · not sent
                      </span>
                    </div>

                    <div className="px-5 py-4 space-y-2.5">
                      <div className="flex gap-3 text-[13px]">
                        <span className="w-16 flex-shrink-0 font-semibold text-stone-500">To</span>
                        <span className="text-ink font-medium">
                          {msg.pendingAction.payload.recipient_name}{" "}
                          <span className="text-stone-500 font-normal">
                            &lt;{msg.pendingAction.payload.to}&gt;
                          </span>
                        </span>
                      </div>
                      {msg.pendingAction.payload.subject && (
                        <div className="flex gap-3 text-[13px]">
                          <span className="w-16 flex-shrink-0 font-semibold text-stone-500">Subject</span>
                          <span className="text-ink font-medium">{msg.pendingAction.payload.subject}</span>
                        </div>
                      )}
                      <div className="flex gap-3 text-[13px]">
                        <span className="w-16 flex-shrink-0 font-semibold text-stone-500">Message</span>
                        <span className="text-ink-light whitespace-pre-wrap leading-relaxed">
                          {msg.pendingAction.payload.body}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center gap-3 px-5 py-3 bg-white/60 border-t border-brass-200">
                      <button
                        onClick={() => resolveAction(msg.id, msg.pendingAction!.id, true)}
                        disabled={resolvingAction === msg.pendingAction.id}
                        className="btn-premium !py-2 !px-5 !text-[13px] rounded-xl"
                      >
                        {resolvingAction === msg.pendingAction.id ? "Sending…" : "Approve & send"}
                      </button>
                      <button
                        onClick={() => resolveAction(msg.id, msg.pendingAction!.id, false)}
                        disabled={resolvingAction === msg.pendingAction.id}
                        className="btn-secondary !py-2 !px-5 !text-[13px] rounded-xl"
                      >
                        Reject
                      </button>
                      <span className="ml-auto text-[10px] text-stone-500 italic">
                        Nothing is sent until you approve
                      </span>
                    </div>
                  </div>
                )}

                {/* Outcome once the user has decided */}
                {msg.actionOutcome && (
                  <div
                    className={`mt-5 flex items-center gap-3 px-4 py-3 rounded-2xl border text-[13px] font-medium ${
                      msg.actionOutcome.status === "sent"
                        ? "bg-sage-50 border-sage-100 text-sage-700"
                        : msg.actionOutcome.status === "rejected"
                        ? "bg-cream-100 border-cream-300 text-stone-600"
                        : "bg-brick-50 border-brick-100 text-brick-700"
                    }`}
                  >
                    {msg.actionOutcome.status === "sent" ? (
                      <CheckIcon className="w-4 h-4 flex-shrink-0" />
                    ) : (
                      <WarningIcon className="w-4 h-4 flex-shrink-0" />
                    )}
                    <span>{msg.actionOutcome.detail}</span>
                  </div>
                )}

                {msg.chart && (
                  <div className="mt-6 p-4 bg-cream-100 border border-cream-300 rounded-2xl overflow-hidden group/chart">
                    <p className="text-[10px] uppercase font-semibold text-brass-600 tracking-widest mb-3 opacity-90">Generated visualization</p>
                    <img
                      src={msg.chart.startsWith('http') ? msg.chart : `${API_BASE}${msg.chart}`}
                      alt="Analytical Chart"
                      className="w-full h-auto rounded-xl shadow-sm border border-brass-100 group-hover/chart:scale-[1.01] transition-transform duration-500 cursor-pointer"
                      onClick={() => setViewerImage({
                        src: msg.chart!.startsWith('http') ? msg.chart! : `${API_BASE}${msg.chart}`,
                        alt: "Analytical Chart"
                      })}
                    />
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[9px] font-semibold text-stone-500 uppercase tracking-tighter italic">Auto-generated from retrieved data</span>
                      <button
                        onClick={() => setViewerImage({
                          src: msg.chart!.startsWith('http') ? msg.chart! : `${API_BASE}${msg.chart}`,
                          alt: "Analytical Chart"
                        })}
                        className="text-[10px] font-semibold text-brass-600 hover:underline"
                      >
                        View full resolution →
                      </button>
                    </div>
                  </div>
                )}

                {/* Numbered Source Citations */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-6 pt-4 border-t border-cream-300">
                    <p className="text-[10px] uppercase font-semibold text-brass-600 tracking-widest mb-3">
                      Cited Sources
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {msg.sources.map((src, i) => (
                        <a key={i} href={src} target="_blank" rel="noreferrer"
                          className="flex items-center gap-2 text-[11px] text-stone-500 hover:text-brass-700 transition-colors group/src"
                          title={src}>
                          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-brass-100 text-brass-800 text-[9px] font-bold flex-shrink-0 group-hover/src:bg-brass-200 transition-colors">
                            {i + 1}
                          </span>
                          <span className="truncate max-w-[400px] font-medium">
                            {src.replace(/^https?:\/\//, "").split("/").slice(0, 3).join("/")}
                          </span>
                        </a>
                      ))}
                    </div>
                  </div>
                )}

                {msg.warning && (
                  <div className="mt-4 flex items-start gap-3 px-4 py-3 bg-brass-50 border border-brass-200 rounded-2xl">
                    <WarningIcon className="w-[18px] h-[18px] text-brass-700 mt-0.5 flex-shrink-0" />
                    <div>
                      <p className="text-[10px] uppercase font-semibold text-brass-700 tracking-widest mb-1">Accuracy notice</p>
                      <p className="text-[12px] text-brass-800 leading-relaxed">{msg.warning}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <span className="text-[10px] text-stone-400 font-semibold mt-2 px-2 uppercase tracking-tighter opacity-60">
              {msg.role} • {hasMounted && msg.timestamp instanceof Date ? msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recently"}
            </span>
          </div>
        ))}

        {/* Live Pipeline Processing Module */}
        {isProcessing && (
          <div className="flex flex-col items-start animate-structural-up">
             <div className="bubble-ai border-brass-200/50 bg-brass-50/40">
                <div className="flex items-center gap-3 mb-4">
                   <span className="w-2 h-2 rounded-full bg-brass-500 animate-ping" />
                   <span className="text-[11px] font-semibold text-brass-700 uppercase tracking-widest">Working on it…</span>
                </div>
                <StageDisplay stages={liveStages} />
             </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Attachment Preview Bar */}
      {(imagePreviews.length > 0 || selectedDocuments.length > 0 || attachedUrls.length > 0) && (
        <div className="px-10 py-3 border-t border-cream-300 bg-cream-50 flex flex-wrap items-center gap-4">
          {imagePreviews.map((preview, idx) => (
            <div key={idx} className="flex items-center gap-3 bg-white p-2 border border-cream-300 rounded-xl shadow-sm">
              <div className="relative group">
                <img src={preview} alt="Preview" className="w-10 h-10 rounded-lg object-cover border border-brass-200" />
                <button
                  onClick={() => clearImage(idx)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-brick-500 text-white rounded-full flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <CloseIcon className="w-2.5 h-2.5" />
                </button>
              </div>
              <div className="max-w-[100px]">
                <p className="text-[10px] font-semibold text-ink truncate">{selectedImages[idx]?.name}</p>
              </div>
            </div>
          ))}
          {selectedDocuments.map((file, idx) => (
            <div key={`doc-${idx}`} className="flex items-center gap-3 bg-white p-2 border border-cream-300 rounded-xl shadow-sm">
              <div className="relative group flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-brass-50 border border-brass-200 flex items-center justify-center text-brass-800">
                  <DocumentIcon className="w-[18px] h-[18px]" />
                </div>
                <button
                  onClick={() => clearDocument(idx)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-brick-500 text-white rounded-full flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <CloseIcon className="w-2.5 h-2.5" />
                </button>
              </div>
              <div className="max-w-[140px]">
                <p className="text-[10px] font-semibold text-ink truncate">{file.name}</p>
                <p className="text-[9px] text-stone-500">{(file.size / 1024).toFixed(1)} KB</p>
              </div>
            </div>
          ))}
          {attachedUrls.map((url, idx) => (
            <div key={`url-${idx}`} className="flex items-center gap-3 bg-white p-2 border border-cream-300 rounded-xl shadow-sm">
              <div className="relative group flex items-center gap-3">
                <div className="w-10 h-10 rounded-lg bg-cream-100 border border-cream-300 flex items-center justify-center text-brass-700">
                  <GlobeIcon className="w-[18px] h-[18px]" />
                </div>
                <button
                  onClick={() => clearUrlAttachment(idx)}
                  className="absolute -top-2 -right-2 w-5 h-5 bg-brick-500 text-white rounded-full flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
                >
                  <CloseIcon className="w-2.5 h-2.5" />
                </button>
              </div>
              <div className="max-w-[180px]">
                <p className="text-[10px] font-semibold text-ink truncate">{url.replace(/^https?:\/\//, "")}</p>
                <p className="text-[9px] text-stone-500">Will crawl into knowledge base</p>
              </div>
            </div>
          ))}
          <div className="ml-auto flex items-center gap-3">
            <p className="text-[10px] text-stone-500">Attachments are processed before the answer</p>
            <button
              onClick={() => {
                clearImage();
                clearDocument();
                clearUrlAttachment();
              }}
              className="text-[10px] font-semibold text-brick-500 hover:underline"
            >
              Clear all
            </button>
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="px-10 py-8 border-t border-cream-300 bg-white">
        <div className="max-w-4xl mx-auto relative group">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-2 items-end bg-cream-50 border-2 border-cream-300 p-2 pr-4 rounded-[28px] focus-within:border-brass-500 focus-within:bg-white shadow-sm transition-all duration-300"
          >
            {/* Image Upload Button */}
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              multiple
              onChange={handleImageSelect}
              className="hidden"
              id="image-upload"
            />
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              className="w-11 h-11 rounded-full bg-cream-100 flex items-center justify-center text-stone-500 hover:text-brass-600 hover:bg-brass-50 transition-colors flex-shrink-0"
              title="Attach an image"
            >
              <ImageIcon className="w-[18px] h-[18px]" />
            </button>

            {/* Document Upload Button */}
            <input
              ref={documentInputRef}
              type="file"
              accept=".pdf,.txt,.md"
              multiple
              onChange={handleDocumentSelect}
              className="hidden"
              id="document-upload"
            />
            <button
              type="button"
              onClick={() => documentInputRef.current?.click()}
              className="w-11 h-11 rounded-full bg-cream-100 flex items-center justify-center text-stone-500 hover:text-brass-600 hover:bg-brass-50 transition-colors flex-shrink-0"
              title="Upload a PDF, TXT, or MD document"
            >
              <DocumentIcon className="w-[18px] h-[18px]" />
            </button>

            {/* URL Crawl Button */}
            <div className="relative flex-shrink-0">
              <button
                type="button"
                onClick={() => setShowUrlInput((value) => !value)}
                className="w-11 h-11 rounded-full bg-cream-100 flex items-center justify-center text-stone-500 hover:text-brass-600 hover:bg-brass-50 transition-colors"
                title="Attach a URL to crawl"
              >
                <GlobeIcon className="w-[18px] h-[18px]" />
              </button>
              {showUrlInput && (
                <div className="absolute bottom-full left-0 mb-3 w-[320px] rounded-3xl bg-white border border-cream-300 shadow-xl p-3 z-50">
                  <div className="flex gap-2">
                    <input
                      type="url"
                      value={urlDraft}
                      onChange={(e) => setUrlDraft(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          e.preventDefault();
                          addUrlAttachment();
                        }
                      }}
                      placeholder="https://example.com"
                      className="flex-1 min-w-0 rounded-2xl border border-cream-300 px-3 py-2 text-xs font-semibold outline-none focus:border-brass-500"
                    />
                    <button
                      type="button"
                      onClick={addUrlAttachment}
                      className="rounded-2xl bg-brass-500 px-4 py-2 text-xs font-semibold text-white hover:bg-brass-600 transition-colors"
                    >
                      Add
                    </button>
                  </div>
                </div>
              )}
            </div>

            <textarea
              ref={inputRef}
              value={input}
              onChange={(e) => {
                setInput(e.target.value);
                e.target.style.height = 'auto';
                e.target.style.height = `${e.target.scrollHeight}px`;
              }}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                  e.preventDefault();
                  if (input.trim() && !isProcessing) {
                    handleSend();
                  }
                }
              }}
              rows={1}
              placeholder={isListening ? "Listening… speak now" : "Ask a question, or attach a document, URL, or image…"}
              className="flex-1 bg-transparent border-none outline-none text-ink font-medium text-[15px] placeholder:text-stone-400 resize-none overflow-y-auto min-h-[24px] max-h-[200px] py-3"
              disabled={isProcessing}
            />

            {/* Voice Input Button */}
            <button
              type="button"
              onClick={toggleVoiceInput}
              disabled={isProcessing}
              className={`w-10 h-10 rounded-full flex items-center justify-center transition-all flex-shrink-0 ${
                isListening
                  ? "bg-brick-500 text-white animate-pulse shadow-lg shadow-brick-100"
                  : "bg-cream-100 text-stone-500 hover:text-brass-600 hover:bg-brass-50"
              }`}
              title={isListening ? "Stop listening" : "Voice input"}
            >
              <MicIcon className="w-[18px] h-[18px]" />
            </button>

            {isProcessing ? (
              <button
                type="button"
                onClick={stopProcessing}
                title="Stop generating"
                aria-label="Stop generating"
                className="w-12 h-12 rounded-full bg-ink text-white flex items-center justify-center shadow-md flex-shrink-0 hover:bg-ink-light transition-colors"
              >
                <StopIcon className="w-4 h-4" />
              </button>
            ) : (
              <button
                type="submit"
                disabled={!input.trim() && selectedImages.length === 0 && selectedDocuments.length === 0 && attachedUrls.length === 0}
                className="btn-premium rounded-[20px] py-3 shadow-md flex-shrink-0"
              >
                <span>Send</span><SendIcon className="w-4 h-4" />
              </button>
            )}
          </form>
          <p className="text-[10px] font-semibold text-stone-500 text-center mt-4 uppercase tracking-[0.2em] opacity-50">
            Documents • Web crawl • Images • Voice • Inline citations
          </p>
        </div>
      </div>
      {/* Image Viewer Modal */}
      {viewerImage && (
        <ImageViewer
          src={viewerImage.src}
          alt={viewerImage.alt}
          onClose={() => setViewerImage(null)}
        />
      )}
    </div>
  );
}
