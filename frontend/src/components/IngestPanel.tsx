"use client";

import { useState, useCallback } from "react";

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
    setUploadStatus({ message: "Initializing neural ingestion...", type: "info" });

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
          message: `Ingestion successful: ${result.chunks} chunks mapped to vector space.`,
          type: "success",
        });
        setFile(null);
      } else {
        setUploadStatus({ message: "Ingestion failed. File integrity check bypassed.", type: "error" });
      }
    } catch (err) {
      setUploadStatus({ message: "Network error during ingestion process.", type: "error" });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <div className="flex flex-col h-full bg-[#FAF9F6]">
      {/* Structural Header */}
      <div className="px-10 py-10 bg-white border-b border-[#F1F1EF] z-10">
        <h2 className="text-2xl font-bold tracking-tight text-[#18181B] font-heading">
          Knowledge Ingress
        </h2>
        <p className="text-xs font-semibold text-[#71717A] mt-1.5 uppercase tracking-widest opacity-60">
          Upload and structure private documentation for the RAG engine
        </p>
      </div>

      <div className="flex-1 overflow-y-auto px-10 py-12">
        <div className="max-w-3xl mx-auto space-y-10">
          
          {/* Upload Hub */}
          <div className="p-10 rounded-[40px] bg-white border-2 border-dashed border-[#E4E4E5] hover:border-[#B45309] transition-all duration-500 group flex flex-col items-center justify-center text-center relative overflow-hidden bg-[radial-gradient(#FBFBF9_1px,transparent_1px)] [background-size:20px_20px] shadow-sm">
             <div className="w-20 h-20 rounded-[28px] bg-[#FAF9F6] border border-[#F1F1EF] flex items-center justify-center text-3xl mb-6 shadow-sm group-hover:scale-110 transition-transform duration-500">
                📂
             </div>
             <h3 className="text-xl font-bold text-[#18181B] font-heading mb-2">Upload Corpus Data</h3>
             <p className="text-sm font-medium text-[#71717A] max-w-[300px] leading-relaxed mx-auto">
                PDF, MD, or TXT documentation for vectorization and semantic mapping.
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
                className="mt-8 text-sm font-bold text-[#B45309] hover:text-[#92400E] cursor-pointer bg-white px-6 py-2.5 rounded-2xl border border-amber-200 shadow-sm transition-all duration-300 hover:shadow-md active:scale-95"
             >
                {file ? "Change Resource" : "Select Document"}
             </label>

             {file && (
                <div className="mt-8 p-4 bg-amber-50 border border-amber-100 rounded-2xl flex items-center gap-4 animate-structural-up">
                   <div className="w-10 h-10 rounded-xl bg-white flex items-center justify-center text-xs font-bold text-amber-900 border border-amber-200">
                      {file.name.split('.').pop()?.toUpperCase()}
                   </div>
                   <div className="text-left">
                      <p className="text-xs font-bold text-amber-900 truncate max-w-[200px]">{file.name}</p>
                      <p className="text-[10px] font-medium text-amber-700 opacity-70">{(file.size / 1024).toFixed(1)} KB Readiness Check: OK</p>
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
                      Ingesting Knowledge...
                   </span>
                ) : (
                   "Trigger Knowledge Sequence →"
                )}
             </button>
             
             {uploadStatus.type && (
                <div className={`mt-8 p-6 rounded-3xl border w-full flex items-center gap-4 animate-structural-up ${
                   uploadStatus.type === "success" ? "bg-green-50 border-green-100 text-green-900" :
                   uploadStatus.type === "error" ? "bg-red-50 border-red-100 text-red-900" :
                   "bg-amber-50 border-amber-100 text-amber-900"
                }`}>
                   <span className="text-2xl">
                      {uploadStatus.type === "success" ? "✅" : uploadStatus.type === "error" ? "❌" : "⚙️"}
                   </span>
                   <div>
                      <p className="text-[10px] font-bold uppercase tracking-widest opacity-60">Sequence Status</p>
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
