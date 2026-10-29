"use client";

import { useState } from "react";

type IconName = "user" | "mail" | "lock";

const ICON_PATHS: Record<IconName, React.ReactNode> = {
  user: (
    <>
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20a7.5 7.5 0 0 1 15 0" />
    </>
  ),
  mail: (
    <>
      <rect x="3" y="5" width="18" height="14" rx="2.5" />
      <path d="m4 7 8 6 8-6" />
    </>
  ),
  lock: (
    <>
      <rect x="4.5" y="10.5" width="15" height="10" rx="2.5" />
      <path d="M8 10.5V7.5a4 4 0 0 1 8 0v3" />
    </>
  ),
};

function FieldIcon({ name }: { name: IconName }) {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      {ICON_PATHS[name]}
    </svg>
  );
}

function EyeIcon({ open }: { open: boolean }) {
  return (
    <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12Z" />
      <circle cx="12" cy="12" r="3" />
      {!open && <path d="M4 20 20 4" />}
    </svg>
  );
}

type AuthFieldProps = {
  id: string;
  label: string;
  type: "text" | "email" | "password";
  value: string;
  onChange: (value: string) => void;
  autoComplete: string;
  icon: IconName;
  /** Entrance stagger position (0, 1, 2, …). */
  index: number;
  error?: string | null;
  /** Extra ids for aria-describedby, e.g. the password checklist. */
  describedBy?: string;
  /** A non-error note under the field (e.g. "Passwords match"). */
  note?: React.ReactNode;
  onFocus?: () => void;
  onBlur?: () => void;
  autoFocus?: boolean;
};

/**
 * A floating-label input. Errors and the Caps Lock warning are linked with aria-describedby;
 * password fields get a show/hide toggle (a real button with aria-pressed).
 */
export default function AuthField({
  id,
  label,
  type,
  value,
  onChange,
  autoComplete,
  icon,
  index,
  error,
  describedBy,
  note,
  onFocus,
  onBlur,
  autoFocus,
}: AuthFieldProps) {
  const [visible, setVisible] = useState(false);
  const [capsLock, setCapsLock] = useState(false);
  const isPassword = type === "password";
  const errorId = `${id}-error`;
  const capsId = `${id}-caps`;
  const noteId = `${id}-note`;
  const describedByIds =
    [error ? errorId : null, capsLock ? capsId : null, note ? noteId : null, describedBy ?? null].filter(Boolean).join(" ") ||
    undefined;

  const checkCaps = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (isPassword) setCapsLock(e.getModifierState("CapsLock"));
  };

  return (
    <div className="auth-depth-field">
      <div className="auth-field-in" style={{ "--auth-i": index } as React.CSSProperties}>
        <div className="relative group">
          <span className="absolute left-4 top-1/2 -translate-y-1/2 text-stone-500 transition-colors group-focus-within:text-brass-600 pointer-events-none">
            <FieldIcon name={icon} />
          </span>
          <input
            id={id}
            name={id}
            type={isPassword && visible ? "text" : type}
            value={value}
            onChange={(e) => onChange(e.target.value)}
            onFocus={onFocus}
            onBlur={() => {
              setCapsLock(false);
              onBlur?.();
            }}
            onKeyDown={checkCaps}
            onKeyUp={checkCaps}
            autoComplete={autoComplete}
            autoFocus={autoFocus}
            spellCheck={false}
            autoCapitalize={type === "text" ? "words" : "none"}
            placeholder=" "
            aria-invalid={error ? true : undefined}
            aria-describedby={describedByIds}
            className={`peer w-full h-14 rounded-2xl bg-cream-50/80 border pl-11 ${isPassword ? "pr-12" : "pr-4"} pt-5 pb-1.5 text-[15px] text-ink outline-none transition-[border-color,box-shadow,background-color] duration-200 focus:bg-white focus:border-brass-500 focus:shadow-[0_0_0_4px_rgb(var(--brass-500)/0.16),0_0_24px_rgb(var(--brass-500)/0.2)] ${
              error ? "border-brick-500" : "border-cream-300 hover:border-cream-400"
            }`}
          />
          <label
            htmlFor={id}
            className="absolute left-11 top-1/2 -translate-y-1/2 text-[15px] text-stone-600 pointer-events-none transition-all duration-200 peer-focus:top-[15px] peer-focus:text-[11px] peer-focus:font-semibold peer-focus:tracking-wide peer-focus:text-brass-700 peer-[:not(:placeholder-shown)]:top-[15px] peer-[:not(:placeholder-shown)]:text-[11px] peer-[:not(:placeholder-shown)]:font-semibold peer-[:not(:placeholder-shown)]:tracking-wide"
          >
            {label}
          </label>
          {isPassword && (
            <button
              type="button"
              onClick={() => setVisible((v) => !v)}
              aria-pressed={visible}
              aria-label={visible ? "Hide password" : "Show password"}
              aria-controls={id}
              className="absolute right-2 top-1/2 -translate-y-1/2 w-10 h-10 flex items-center justify-center rounded-xl text-stone-500 hover:text-brass-700 hover:bg-cream-100 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass-500 transition-colors"
            >
              <EyeIcon open={!visible} />
            </button>
          )}
        </div>
        {capsLock && (
          <p id={capsId} className="mt-1.5 px-1 text-[12px] font-medium text-brass-700" aria-live="polite">
            Caps Lock is on
          </p>
        )}
        {error ? (
          <p id={errorId} className="mt-1.5 px-1 text-[12px] font-medium text-brick-700">
            {error}
          </p>
        ) : note ? (
          <p id={noteId} className="mt-1.5 px-1 text-[12px] font-medium text-sage-700">
            {note}
          </p>
        ) : null}
      </div>
    </div>
  );
}

/** Full-width gradient submit button with a shine sweep; shows a spinner while pending. */
export function SubmitButton({
  label,
  pendingLabel,
  pending,
  disabled,
  index,
}: {
  label: string;
  pendingLabel: string;
  pending: boolean;
  disabled: boolean;
  index: number;
}) {
  return (
    <div className="auth-depth-button">
      <div className="auth-field-in" style={{ "--auth-i": index } as React.CSSProperties}>
        <button
          type="submit"
          disabled={disabled || pending}
          aria-busy={pending}
          className="auth-btn w-full h-[52px] rounded-2xl text-[15px] font-semibold tracking-[0.01em] flex items-center justify-center gap-2.5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-500"
        >
          {pending ? (
            <>
              <span className="auth-spinner" aria-hidden="true" />
              {pendingLabel}
            </>
          ) : (
            <>
              {label}
              <svg viewBox="0 0 24 24" className="w-[18px] h-[18px]" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <path d="M5 12h14M13 6l6 6-6 6" />
              </svg>
            </>
          )}
        </button>
      </div>
    </div>
  );
}
