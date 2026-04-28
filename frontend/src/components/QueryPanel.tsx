"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000";

type Message = {
  id: string;
  role: "user" | "assistant" | "system";
  content: string;
  sources?: string[];
  source_map?: Record<string, string>;
  chart?: string;
  warning?: string;
  timestamp: Date;
  pipeline?: PipelineStage[];
  image?: string; // base64 preview of uploaded image
};

type PipelineStage = {
  model: string;
  status: string;
  action: string;
  details?: any;
};

// Moving StageDisplay outside the component to prevent re-creation on every render
const StageDisplay = ({ stages }: { stages: PipelineStage[] }) => (
  <div className="flex flex-col gap-2 p-4 bg-[#FAF9F6] border border-[#F1F1EF] rounded-3xl mt-4 max-w-[500px]">
    <p className="text-[10px] font-bold text-[#B45309] uppercase tracking-[0.1em] mb-2 opacity-80">Pipeline Execution Path</p>
    {stages.map((stage, i) => (
      <div key={i} className="flex items-center gap-3 text-[11px] font-medium text-[#71717A]">
        <span className={`w-1.5 h-1.5 rounded-full ${
          stage.status === 'Processing' ? 'bg-[#FF9100] animate-pulse' : 
          stage.status === 'Completed' ? 'bg-[#16A34A]' : 'bg-[#E4E4E5]'
        }`} />
        <span className="text-[#18181B] font-bold min-w-[140px] text-xs">{stage.model}</span>
        <span className="truncate opacity-70 italic">{stage.action}</span>
      </div>
    ))}
  </div>
);

export default function QueryPanel() {
  const [hasMounted, setHasMounted] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [isProcessing, setIsProcessing] = useState(false);
  const [liveStages, setLiveStages] = useState<PipelineStage[]>([]);
  
  // Voice input state
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);
  
  // Image upload state
  const [selectedImage, setSelectedImage] = useState<File | null>(null);
  const [imagePreview, setImagePreview] = useState<string | null>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);
  
  useEffect(() => {
    setHasMounted(true);
    setMessages([
      {
        id: "welcome",
        role: "system",
        content:
          "Welcome to your Professional AI Workspace. Upload documents, crawl websites, or attach images to begin. You can also use the 🎤 microphone for voice input.",
        timestamp: new Date(),
      },
    ]);
  }, []);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  
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

  // ─── Image Upload Logic ──────────────────────────────────────────
  const handleImageSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      setSelectedImage(file);
      const reader = new FileReader();
      reader.onloadend = () => {
        setImagePreview(reader.result as string);
      };
      reader.readAsDataURL(file);
    }
  };

  const clearImage = () => {
    setSelectedImage(null);
    setImagePreview(null);
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  };

  // ─── Send Logic (supports text-only and text+image) ──────────────
  const handleSend = useCallback(() => {
    const query = input.trim();
    if (!query || isProcessing) return;

    const userMsg: Message = {
      id: Date.now().toString(),
      role: "user",
      content: query,
      timestamp: new Date(),
      image: imagePreview || undefined,
    };
    
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setIsProcessing(true);
    setLiveStages([]);

    // If we have an image, use POST with FormData
    if (selectedImage) {
      const formData = new FormData();
      formData.append("query", query);
      formData.append("image", selectedImage);

      // For POST+SSE we need to use fetch + ReadableStream
      fetch(`${API_BASE}/api/stream`, {
        method: "POST",
        body: formData,
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
      }).catch(() => {
        setMessages((prev) => [...prev, {
          id: (Date.now() + 2).toString(),
          role: "system",
          content: "Failed to process image. Ensure backend is running on Port 8000.",
          timestamp: new Date(),
        }]);
        setIsProcessing(false);
        setLiveStages([]);
      });

      clearImage();
    } else {
      // Text-only: use EventSource (GET)
      const eventSource = new EventSource(
        `${API_BASE}/api/stream?query=${encodeURIComponent(query)}`
      );

      eventSource.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          const isFinal = handleSSEData(data);
          if (isFinal) {
            eventSource.close();
          }
        } catch (err) {
          console.error("Critical SSE parse error:", err);
        }
      };

      eventSource.onerror = () => {
        const errorMsg: Message = {
          id: (Date.now() + 2).toString(),
          role: "system",
          content: "Network integrity compromised. Ensure your local framework host is active on Port 8000.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, errorMsg]);
        setIsProcessing(false);
        setLiveStages([]);
        eventSource.close();
      };
    }
  }, [input, isProcessing, selectedImage, imagePreview]);

  // Shared SSE data handler — returns true if it's the final response
  const handleSSEData = (data: any): boolean => {
    if (data.model === "Final Response" && data.status === "Completed") {
      setMessages((prev) => {
        const aiMsg: Message = {
          id: (Date.now() + 1).toString(),
          role: "assistant",
          content: data.details?.answer || "Analytical synthesis produced no tangible result.",
          sources: data.details?.sources || [],
          source_map: data.details?.source_map || undefined,
          chart: data.details?.chart || undefined,
          warning: data.details?.warning || undefined,
          timestamp: new Date(),
          pipeline: [...stagesRef.current, data].map(stage =>
            stage.model === data.model ? data : stage
          ),
        };
        return [...prev, aiMsg];
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
            className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-amber-100 text-amber-800 text-[9px] font-bold no-underline hover:bg-amber-200 transition-colors align-super ml-0.5 mr-0.5 cursor-pointer"
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
      {/* Structural Header */}
      <div className="px-10 py-8 border-b border-[#F1F1EF] bg-white z-10 flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-[#18181B] font-heading">
            Neural Analysis Interface
          </h2>
          <p className="text-xs font-medium text-[#71717A] mt-1.5 uppercase tracking-wide opacity-60">
            Professional Multi-Agent Retrieval Framework
          </p>
        </div>
        <div className="flex items-center gap-4">
           {isProcessing && (
              <div className="flex items-center gap-2 group relative">
                <div className="flex items-center gap-2 px-3 py-1.5 bg-amber-50 border border-amber-100 rounded-full text-[11px] font-bold text-amber-700">
                  <span className="w-1.5 h-1.5 rounded-full bg-amber-600 animate-ping" />
                  Processing
                </div>
                <button 
                  onClick={() => setIsProcessing(false)}
                  className="hidden group-hover:block absolute right-0 top-full mt-2 px-2 py-1 bg-red-50 text-red-600 text-[9px] font-bold rounded border border-red-100 whitespace-nowrap shadow-sm z-50"
                >
                  Force Reset ❌
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
                msg.role === "system" ? "text-center mx-auto text-[11px] text-[#71717A] italic opacity-60 py-4 max-w-[400px]" : 
                "bubble-ai"
              }`}
            >
              <div className="relative">
                {msg.role === "assistant" && msg.pipeline && (
                  <StageDisplay stages={msg.pipeline} />
                )}
                
                {/* User image preview */}
                {msg.role === "user" && msg.image && (
                  <div className="mb-3 rounded-xl overflow-hidden border border-white/20 max-w-[200px]">
                    <img src={msg.image} alt="Uploaded" className="w-full h-auto" />
                  </div>
                )}

                <div className={`text-[15px] leading-[1.65] font-medium ${msg.role === "assistant" ? "mt-4 text-[#27272A] prose prose-zinc max-w-none prose-sm prose-headings:mb-2 prose-p:mb-2 prose-table:border prose-table:border-zinc-200 prose-th:bg-zinc-50 prose-th:px-3 prose-th:py-2 prose-td:px-3 prose-td:py-2" : ""}`}>
                  {msg.role === "assistant" ? (
                    renderCitedContent(msg.content, msg.source_map)
                  ) : (
                    msg.content
                  )}
                </div>

                {msg.chart && (
                  <div className="mt-6 p-4 bg-[#FAF9F6] border border-[#F1F1EF] rounded-2xl overflow-hidden group/chart">
                    <p className="text-[10px] uppercase font-bold text-[#B45309] tracking-widest mb-3 opacity-60">Generated Analytical Visualization</p>
                    <img 
                      src={msg.chart.startsWith('http') ? msg.chart : `${API_BASE}${msg.chart}`} 
                      alt="Analytical Chart"
                      className="w-full h-auto rounded-xl shadow-sm border border-amber-100 group-hover/chart:scale-[1.01] transition-transform duration-500"
                    />
                    <div className="mt-3 flex items-center justify-between">
                      <span className="text-[9px] font-bold text-[#71717A] uppercase tracking-tighter italic">Auto-Generated Data Visualization</span>
                      <a 
                        href={msg.chart.startsWith('http') ? msg.chart : `${API_BASE}${msg.chart}`} 
                        target="_blank" 
                        rel="noreferrer"
                        className="text-[10px] font-bold text-[#B45309] hover:underline"
                      >
                        View High Resolution →
                      </a>
                    </div>
                  </div>
                )}
                
                {/* Numbered Source Citations */}
                {msg.sources && msg.sources.length > 0 && (
                  <div className="mt-6 pt-4 border-t border-[#F1F1EF]">
                    <p className="text-[10px] uppercase font-bold text-[#B45309] tracking-widest mb-3">
                      📚 Cited Sources
                    </p>
                    <div className="flex flex-col gap-1.5">
                      {msg.sources.map((src, i) => (
                        <a key={i} href={src} target="_blank" rel="noreferrer"
                          className="flex items-center gap-2 text-[11px] text-[#71717A] hover:text-amber-700 transition-colors group/src"
                          title={src}>
                          <span className="inline-flex items-center justify-center w-5 h-5 rounded-full bg-amber-100 text-amber-800 text-[9px] font-bold flex-shrink-0 group-hover/src:bg-amber-200 transition-colors">
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
                  <div className="mt-4 flex items-start gap-3 px-4 py-3 bg-amber-50 border border-amber-200 rounded-2xl">
                    <span className="text-lg mt-0.5">⚠️</span>
                    <div>
                      <p className="text-[10px] uppercase font-bold text-amber-700 tracking-widest mb-1">Accuracy Notice</p>
                      <p className="text-[12px] text-amber-800 leading-relaxed">{msg.warning}</p>
                    </div>
                  </div>
                )}
              </div>
            </div>
            <span className="text-[10px] text-[#A1A1AA] font-bold mt-2 px-2 uppercase tracking-tighter opacity-50">
              {msg.role} • {hasMounted && msg.timestamp instanceof Date ? msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : "Recently"}
            </span>
          </div>
        ))}

        {/* Live Pipeline Processing Module */}
        {isProcessing && (
          <div className="flex flex-col items-start animate-structural-up">
             <div className="bubble-ai border-amber-200/50 bg-[#FFFCF8]">
                <div className="flex items-center gap-3 mb-4">
                   <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping" />
                   <span className="text-[11px] font-bold text-amber-700 uppercase tracking-widest">Active Neural Routing...</span>
                </div>
                <StageDisplay stages={liveStages} />
             </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Image Preview Bar */}
      {imagePreview && (
        <div className="px-10 py-3 border-t border-[#F1F1EF] bg-[#FEFDFB] flex items-center gap-3">
          <div className="relative group">
            <img src={imagePreview} alt="Preview" className="w-14 h-14 rounded-xl object-cover border border-amber-200 shadow-sm" />
            <button
              onClick={clearImage}
              className="absolute -top-2 -right-2 w-5 h-5 bg-red-500 text-white text-[10px] rounded-full flex items-center justify-center shadow-md opacity-0 group-hover:opacity-100 transition-opacity"
            >
              ✕
            </button>
          </div>
          <div>
            <p className="text-[11px] font-bold text-[#18181B]">{selectedImage?.name}</p>
            <p className="text-[10px] text-[#71717A]">Image attached — will be analyzed by Vision AI</p>
          </div>
        </div>
      )}

      {/* Structural Input Area */}
      <div className="px-10 py-10 border-t border-[#F1F1EF] bg-white">
        <div className="max-w-4xl mx-auto relative group">
          <form
            onSubmit={(e) => {
              e.preventDefault();
              handleSend();
            }}
            className="flex gap-3 items-center bg-[#FCFBFA] border-2 border-[#F1F1EF] p-2 pr-4 rounded-[28px] focus-within:border-[#B45309] focus-within:bg-white shadow-sm transition-all duration-300"
          >
            {/* Image Upload Button */}
            <input
              ref={imageInputRef}
              type="file"
              accept="image/*"
              onChange={handleImageSelect}
              className="hidden"
              id="image-upload"
            />
            <button
              type="button"
              onClick={() => imageInputRef.current?.click()}
              className="w-12 h-12 rounded-full bg-[#FAF9F6] flex items-center justify-center text-xl text-[#71717A] hover:text-[#B45309] hover:bg-amber-50 transition-colors flex-shrink-0"
              title="Attach an image"
            >
              📎
            </button>

            <input
              ref={inputRef}
              type="text"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder={isListening ? "🎤 Listening... speak now" : "Submit query to the MultiModel RAG Framework..."}
              className="flex-1 bg-transparent border-none outline-none text-[#18181B] font-medium text-[15px] placeholder:text-[#A1A1AA]"
              disabled={isProcessing}
            />

            {/* Voice Input Button */}
            <button
              type="button"
              onClick={toggleVoiceInput}
              disabled={isProcessing}
              className={`w-10 h-10 rounded-full flex items-center justify-center text-lg transition-all flex-shrink-0 ${
                isListening 
                  ? "bg-red-500 text-white animate-pulse shadow-lg shadow-red-200" 
                  : "bg-[#FAF9F6] text-[#71717A] hover:text-[#B45309] hover:bg-amber-50"
              }`}
              title={isListening ? "Stop listening" : "Voice input"}
            >
              🎤
            </button>

            <button
              type="submit"
              disabled={!input.trim()}
              className="btn-premium rounded-[20px] py-3 shadow-md flex-shrink-0"
            >
              {isProcessing ? "Processing..." : "Analyze →"}
            </button>
          </form>
          <p className="text-[10px] font-bold text-[#71717A] text-center mt-4 uppercase tracking-[0.2em] opacity-40">
            🎤 Voice Input • 📎 Image Analysis • 📚 Inline Citations
          </p>
        </div>
      </div>
    </div>
  );
}
