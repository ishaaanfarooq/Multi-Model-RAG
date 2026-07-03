"use client";

import { useState } from "react";
import { UploadCloudIcon, CheckIcon, WarningIcon, DocumentIcon } from "@/components/icons";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export default function IngestPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [uploadStatus, setUploadStatus] = useState<{
    message: string;
    type: "success" | "error" | "info" | null;
  }>({ message: "", type: null });

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
    }
  };

  const handleUpload = async () => {
    if (!file) return;

    setIsUploading(true);
    setUploadStatus({ message: "Reading and chunking document…", type: "info" });

    const formData = new FormData();
    formData.append("file", file);

    try {
      const response = await fetch(`${API_BASE}/api/ingest`, {
        method: "POST",
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        setUploadStatus({
          message: `Ingested successfully — ${result.chunks} chunks added to the knowledge base.`,
          type: "success",
        });
        setFile(null);
      } else {
        setUploadStatus({ message: "Ingestion failed. Please check the file and try again.", type: "error" });
      }
    } catch (err) {
      setUploadStatus({ message: "Network error while reaching the backend.", type: "error" });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-cream-100">
      {/* Header */}
      <div className="px-10 py-10 bg-white border-b border-cream-300 z-10">
        <h2 className="text-2xl font-semibold tracking-tight text-ink font-heading">
          Documents
        </h2>
        <p className="text-xs font-medium text-stone-500 mt-1.5 uppercase tracking-widest opacity-70">
          Upload files to add to your searchable knowledge base
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-12">
        <div className="max-w-3xl mx-auto space-y-10">

          {/* Upload Hub */}
          <div className="p-10 rounded-[40px] bg-white border-2 border-dashed border-cream-300 hover:border-brass-400 transition-all duration-500 group flex flex-col items-center justify-center text-center relative overflow-hidden shadow-sm">
             <div className="w-20 h-20 rounded-[28px] bg-cream-100 border border-cream-300 flex items-center justify-center text-brass-600 mb-6 shadow-sm group-hover:scale-105 transition-transform duration-500">
                <UploadCloudIcon className="w-8 h-8" />
             </div>
             <h3 className="text-xl font-semibold text-ink font-heading mb-2">Upload a document</h3>
             <p className="text-sm font-medium text-stone-500 max-w-[320px] leading-relaxed mx-auto">
                PDF, Markdown, or plain text — it will be chunked, embedded, and made searchable.
             </p>

             <input
                id="file-upload"
                type="file"
                onChange={handleFileChange}
                className="hidden"
                accept=".pdf,.txt,.md"
                disabled={isUploading}
             />
             <label
                htmlFor="file-upload"
                className="mt-8 text-sm font-semibold text-brass-700 hover:text-brass-800 cursor-pointer bg-white px-6 py-2.5 rounded-2xl border border-brass-200 shadow-sm transition-all duration-300 hover:shadow-md active:scale-95"
             >
                {file ? "Change file" : "Select a file"}
             </label>

             {file && (
                <div className="mt-8 p-4 bg-brass-50 border border-brass-100 rounded-2xl flex items-center gap-4 animate-structural-up">
                   <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center text-brass-700 border border-brass-200">
                      <DocumentIcon className="w-5 h-5" />
                   </div>
                   <div className="text-left">
                      <p className="text-xs font-semibold text-brass-900 truncate max-w-[240px]">{file.name}</p>
                      <p className="text-[10px] font-medium text-brass-700 opacity-80">{(file.size / 1024).toFixed(1)} KB · ready to ingest</p>
                   </div>
                </div>
             )}
          </div>

          {/* Action Module */}
          <div className="flex flex-col items-center">
             <button
                onClick={handleUpload}
                disabled={!file || isUploading}
                className="btn-premium rounded-[24px] py-4 px-12 text-base shadow-xl min-w-[300px]"
             >
                {isUploading ? (
                   <span className="flex items-center gap-3">
                      <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                      Ingesting…
                   </span>
                ) : (
                   "Upload & Ingest"
                )}
             </button>

             {uploadStatus.type && (
                <div className={`mt-8 p-6 rounded-3xl border w-full flex items-center gap-4 animate-structural-up ${
                   uploadStatus.type === "success" ? "bg-sage-50 border-sage-100 text-sage-700" :
                   uploadStatus.type === "error" ? "bg-brick-50 border-brick-100 text-brick-700" :
                   "bg-brass-50 border-brass-100 text-brass-800"
                }`}>
                   <span className="flex-shrink-0">
                      {uploadStatus.type === "success" ? <CheckIcon className="w-6 h-6" /> : uploadStatus.type === "error" ? <WarningIcon className="w-6 h-6" /> : <UploadCloudIcon className="w-6 h-6" />}
                   </span>
                   <div>
                      <p className="text-[10px] font-semibold uppercase tracking-widest opacity-70">Status</p>
                      <p className="text-sm font-semibold">{uploadStatus.message}</p>
                   </div>
                </div>
             )}
          </div>
        </div>
      </div>
    </div>
  );
}
