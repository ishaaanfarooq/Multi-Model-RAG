"use client";

import { useEffect } from "react";
import { WarningIcon } from "@/components/icons";

interface ConfirmDialogProps {
  open: boolean;
  title: string;
  message: React.ReactNode;
  confirmLabel?: string;
  cancelLabel?: string;
  destructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * A styled confirmation modal that matches the workspace theme, replacing the
 * browser's native confirm(). Closes on Escape or backdrop click.
 */
export default function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  cancelLabel = "Cancel",
  destructive = false,
  onConfirm,
  onCancel,
}: ConfirmDialogProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCancel();
      if (e.key === "Enter") onConfirm();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onCancel, onConfirm]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[200] flex items-center justify-center bg-ink/40 backdrop-blur-sm animate-structural-up"
      onClick={onCancel}
    >
      <div
        className="w-[380px] max-w-[90vw] bg-white rounded-3xl border border-cream-300 shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        role="dialog"
        aria-modal="true"
      >
        <div className="p-6">
          <div className="flex items-start gap-4">
            <div
              className={`w-11 h-11 rounded-2xl flex items-center justify-center flex-shrink-0 ${
                destructive ? "bg-brick-50 text-brick-600" : "bg-brass-50 text-brass-600"
              }`}
            >
              <WarningIcon className="w-5 h-5" />
            </div>
            <div className="flex-1 min-w-0 pt-0.5">
              <h3 className="text-base font-semibold text-ink font-heading">{title}</h3>
              <div className="text-sm text-stone-600 mt-1.5 leading-relaxed">{message}</div>
            </div>
          </div>
        </div>

        <div className="flex items-center justify-end gap-3 px-6 py-4 bg-cream-50 border-t border-cream-300">
          <button
            onClick={onCancel}
            className="px-5 py-2 rounded-xl text-sm font-semibold text-stone-600 hover:bg-cream-100 transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            onClick={onConfirm}
            className={`px-5 py-2 rounded-xl text-sm font-semibold text-white shadow-sm transition-colors ${
              destructive ? "bg-brick-500 hover:bg-brick-700" : "bg-brass-500 hover:bg-brass-600"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
