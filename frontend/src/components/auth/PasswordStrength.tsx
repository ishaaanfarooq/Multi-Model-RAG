"use client";

import { passwordChecks } from "@/components/auth/validation";

const LEVELS = [
  { label: "Weak", bar: "bg-brick-500", text: "text-brick-700" },
  { label: "Fair", bar: "bg-brass-400", text: "text-brass-700" },
  { label: "Good", bar: "bg-sage-500", text: "text-sage-700" },
  { label: "Strong", bar: "bg-sage-700", text: "text-sage-700" },
];

/**
 * Register only: four segments that fill as the password improves, and the rules as a checklist.
 * A symbol is optional; it only raises the score. Score = rules met, capped at 1 until 8+ bytes.
 */
export default function PasswordStrength({ id, password }: { id: string; password: string }) {
  const c = passwordChecks(password);
  const met = Number(c.length) + Number(c.letter) + Number(c.number) + Number(c.symbol);
  const score = !password ? 0 : c.length && !c.tooLong ? met : Math.min(met, 1);
  const level = LEVELS[Math.max(score, 1) - 1];
  const items = [
    { ok: c.length && !c.tooLong, label: c.tooLong ? "At most 72 bytes" : "8+ characters" },
    { ok: c.letter, label: "A letter" },
    { ok: c.number, label: "A number" },
    { ok: c.symbol, label: "A symbol (optional)" },
  ];

  return (
    <div className="auth-depth-field" id={id}>
      <div className="auth-field-in px-1" style={{ "--auth-i": 3 } as React.CSSProperties}>
        <div className="flex items-center gap-1.5" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <div key={i} className="auth-seg" data-on={i < score}>
              <span className={level.bar} style={{ transitionDelay: `${i * 50}ms` }} />
            </div>
          ))}
        </div>
        <div className="mt-2 flex items-start justify-between gap-3">
          <ul className="grid grid-cols-2 gap-x-4 gap-y-1 text-[12px]">
            {items.map((item) => (
              <li key={item.label} className={`flex items-center gap-1.5 ${item.ok ? "text-sage-700" : "text-stone-600"}`}>
                <svg viewBox="0 0 16 16" className="w-3.5 h-3.5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  {item.ok ? <path d="m3.5 8.5 3 3 6-7" /> : <circle cx="8" cy="8" r="2" fill="currentColor" stroke="none" />}
                </svg>
                {item.label}
                <span className="sr-only">{item.ok ? " (done)" : " (not yet)"}</span>
              </li>
            ))}
          </ul>
          <p className={`text-[12px] font-semibold whitespace-nowrap ${password ? level.text : "text-stone-600"}`} aria-live="polite">
            {password ? level.label : "Strength"}
          </p>
        </div>
      </div>
    </div>
  );
}
