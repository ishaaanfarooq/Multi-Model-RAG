"use client";

import { useEffect, useId, useRef } from "react";

/** Praxis mark: a hexagonal core, echoing the 3D scene. */
export function PraxisMark({ className = "w-8 h-8" }: { className?: string }) {
  // The mark can appear twice on one page (mobile brand line + card header): keep gradient ids unique.
  const gradientId = `auth-mark-${useId().replace(/:/g, "")}`;
  return (
    <svg viewBox="0 0 48 48" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" stopColor="rgb(var(--brass-400))" />
          <stop offset="1" stopColor="rgb(var(--brass-600))" />
        </linearGradient>
      </defs>
      <path d="M24 3 42 13.5v21L24 45 6 34.5v-21Z" fill="none" stroke="rgb(var(--brass-500))" strokeWidth="2.2" strokeLinejoin="round" />
      <path d="M24 13 33 18.5v11L24 35l-9-5.5v-11Z" fill={`url(#${gradientId})`} />
      <path d="M24 13v22M15 18.5l18 11M33 18.5l-18 11" stroke="rgb(var(--white))" strokeOpacity="0.45" strokeWidth="1" />
    </svg>
  );
}

/** Brand row, title and subtitle, lifted 40px towards the viewer. */
export function CardHeader({ title, subtitle }: { title: string; subtitle: string }) {
  return (
    <div className="auth-depth-header">
      <div className="flex items-center gap-2.5">
        <PraxisMark className="w-9 h-9" />
        <span className="font-heading font-serif text-[22px] font-semibold tracking-tight text-ink">Praxis</span>
      </div>
      <h1 className="font-heading font-serif mt-6 text-[30px] sm:text-[32px] font-semibold leading-tight tracking-tight text-ink">
        {title}
      </h1>
      <p className="mt-1.5 text-[14px] leading-relaxed text-stone-600">{subtitle}</p>
    </div>
  );
}

/**
 * The glass card. Tilts up to 7° towards the pointer with a specular glare, springs back on
 * leave, and shakes when `shakeKey` changes. Tilt is off for coarse pointers and reduced motion.
 * The glass sits outside the preserve-3d element and copies its tilt from the shared CSS
 * variables: Chrome skips backdrop-filter inside a preserve-3d context, and a backdrop-filter on
 * the content's parent would flatten the content's depth layers.
 */
export default function TiltCard({ children, shakeKey }: { children: React.ReactNode; shakeKey: number }) {
  const frameRef = useRef<HTMLDivElement>(null);
  const shakeRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const frame = frameRef.current;
    const tilt = shakeRef.current; // holds the tilt variables for both the glass and the content
    if (!frame || !tilt) return;
    const noTilt = window.matchMedia("(pointer: coarse), (prefers-reduced-motion: reduce)");
    let raf = 0;

    const reset = () => {
      cancelAnimationFrame(raf);
      tilt.dataset.active = "false";
      tilt.style.setProperty("--auth-rx", "0deg");
      tilt.style.setProperty("--auth-ry", "0deg");
    };
    const onMove = (e: PointerEvent) => {
      if (noTilt.matches || e.pointerType === "touch") return;
      // Measure the untransformed frame, not the tilting card, so the tilt cannot feed back on itself.
      const r = frame.getBoundingClientRect();
      const x = clampUnit((e.clientX - r.left) / r.width);
      const y = clampUnit((e.clientY - r.top) / r.height);
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        tilt.dataset.active = "true";
        tilt.style.setProperty("--auth-ry", `${((x - 0.5) * 14).toFixed(2)}deg`);
        tilt.style.setProperty("--auth-rx", `${((0.5 - y) * 14).toFixed(2)}deg`);
        tilt.style.setProperty("--auth-gx", `${(x * 100).toFixed(1)}%`);
        tilt.style.setProperty("--auth-gy", `${(y * 100).toFixed(1)}%`);
      });
    };

    frame.addEventListener("pointermove", onMove);
    frame.addEventListener("pointerleave", reset);
    noTilt.addEventListener("change", reset);
    return () => {
      cancelAnimationFrame(raf);
      frame.removeEventListener("pointermove", onMove);
      frame.removeEventListener("pointerleave", reset);
      noTilt.removeEventListener("change", reset);
    };
  }, []);

  // Restart the shake on every error, including back-to-back ones.
  useEffect(() => {
    const el = shakeRef.current;
    if (!el || shakeKey === 0) return;
    el.classList.remove("auth-shake");
    void el.offsetWidth; // reflow so the animation starts again
    el.classList.add("auth-shake");
    const done = () => el.classList.remove("auth-shake");
    el.addEventListener("animationend", done, { once: true });
    return () => el.removeEventListener("animationend", done);
  }, [shakeKey]);

  return (
    <div ref={frameRef} className="auth-card-enter">
      <div ref={shakeRef} className="relative">
        <div aria-hidden="true" className="auth-glass" />
        <div className="auth-tilt relative">
          <div aria-hidden="true" className="auth-border" />
          <div aria-hidden="true" className="auth-glare" />
          <div className="auth-3d relative px-6 py-7 sm:px-9 sm:py-9">{children}</div>
        </div>
      </div>
    </div>
  );
}

function clampUnit(v: number) {
  return Math.min(1, Math.max(0, v));
}
