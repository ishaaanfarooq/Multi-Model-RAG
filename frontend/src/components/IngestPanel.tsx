"use client";

import { useState, useRef, useCallback } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type IngestResult = {
  filename: string;
  chunks: number;
  status: string;
};

export default function IngestPanel() {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadProgress, setUploadProgress] = useState(0);
  const [results, setResults] = useState<IngestResult[]>([]);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleUpload = useCallback(async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setError(null);
    setIsUploading(true);
    setUploadProgress(0);

    const totalFiles = files.length;
    let completed = 0;

    for (const file of Array.from(files)) {
      const formData = new FormData();
      formData.append("file", file);

      try {
        const res = await fetch(`${API_BASE}/api/ingest`, {
          method: "POST",
          body: formData,
        });

        if (!res.ok) {
          const errData = await res.json().catch(() => ({}));
          throw new Error(errData.detail || `Upload failed: ${res.statusText}`);
        }

        const data = await res.json();
        setResults((prev) => [
          { filename: data.filename, chunks: data.chunks, status: data.status },
          ...prev,
        ]);
      } catch (err: any) {
        setError(err.message || "Upload failed");
      }

      completed++;
      setUploadProgress(Math.round((completed / totalFiles) * 100));
    }

    setIsUploading(false);
    setUploadProgress(0);
  }, []);

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => setIsDragging(false);

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    handleUpload(e.dataTransfer.files);
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="px-6 py-4 border-b border-[var(--color-border)]">
        <h2 className="text-xl font-bold tracking-tight">📄 Upload Documents</h2>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          Upload PDF, TXT, or Markdown files to build your knowledge base
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-6 py-6 space-y-6">
        {/* Drop Zone */}
        <div
          className={`dropzone ${isDragging ? "active" : ""}`}
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => fileInputRef.current?.click()}
        >
          <input
            ref={fileInputRef}
            type="file"
            className="hidden"
            accept=".pdf,.txt,.md"
            multiple
            onChange={(e) => handleUpload(e.target.files)}
          />
          <div className="text-4xl mb-3">📎</div>
          <p className="text-sm font-medium text-[var(--color-foreground)]">
            {isDragging ? "Drop files here..." : "Drag & drop files here, or click to browse"}
          </p>
          <p className="text-xs text-[var(--color-muted)] mt-2">
            Supported: PDF, TXT, Markdown
          </p>
          <div className="flex justify-center gap-2 mt-4">
            <span className="badge badge-info">.pdf</span>
            <span className="badge badge-info">.txt</span>
            <span className="badge badge-info">.md</span>
          </div>
        </div>

        {/* Upload Progress */}
        {isUploading && (
          <div className="glass-panel p-4 animate-slide-up">
            <div className="flex items-center justify-between mb-2">
              <span className="text-sm font-medium">Uploading & Indexing...</span>
              <span className="text-xs text-[var(--color-accent)]">{uploadProgress}%</span>
            </div>
            <div className="w-full h-2 rounded-full bg-[var(--color-border)] overflow-hidden">
              <div
                className="h-full accent-gradient rounded-full transition-all duration-300"
                style={{ width: `${uploadProgress}%` }}
              />
            </div>
          </div>
        )}

        {/* Error */}
        {error && (
          <div className="glass-panel p-4 border-[var(--color-error)] animate-slide-up">
            <div className="flex items-center gap-2">
              <span className="text-[var(--color-error)]">⚠️</span>
              <p className="text-sm text-[var(--color-error)]">{error}</p>
            </div>
          </div>
        )}

        {/* Results */}
        {results.length > 0 && (
          <div>
            <h3 className="text-sm font-semibold text-[var(--color-muted)] uppercase tracking-wider mb-3">
              Ingested Documents
            </h3>
            <div className="space-y-2">
              {results.map((res, i) => (
                <div
                  key={i}
                  className="glass-panel-solid p-4 flex items-center justify-between animate-slide-up"
                >
                  <div className="flex items-center gap-3">
                    <span className="text-lg">
                      {res.filename.endsWith(".pdf")
                        ? "📕"
                        : res.filename.endsWith(".md")
                        ? "📝"
                        : "📃"}
                    </span>
                    <div>
                      <p className="text-sm font-medium">{res.filename}</p>
                      <p className="text-xs text-[var(--color-muted)]">{res.chunks} chunks indexed</p>
                    </div>
                  </div>
                  <span className="badge badge-success">✓ Ingested</span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
