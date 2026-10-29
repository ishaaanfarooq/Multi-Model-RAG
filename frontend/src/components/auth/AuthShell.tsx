"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef } from "react";
import { usePathname } from "next/navigation";
import { useTheme } from "@/lib/theme";
import AuthScene, { type AuthSignal, type AuthView } from "@/components/auth/AuthScene";
import { PraxisMark } from "@/components/auth/TiltCard";

type SceneApi = { signal: (event: AuthSignal) => void };

const AuthSceneContext = createContext<SceneApi>({ signal: () => {} });

/** Lets the forms drive the 3D scene (keystrokes, privacy mode, submit, error, success). */
export const useAuthScene = () => useContext(AuthSceneContext);

export const prefersReducedMotion = () =>
  typeof window !== "undefined" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;

// Only facts from summary.md: hybrid FAISS + BM25 retrieval, the verifier, local Ollama inference.
const FEATURES = [
  { label: "Hybrid retrieval · FAISS + BM25", depth: 16, delay: "0s", indent: "ml-0" },
  { label: "Self-verifying answers", depth: 30, delay: "-2.4s", indent: "ml-14" },
  { label: "Runs locally on Ollama", depth: 10, delay: "-4.8s", indent: "ml-5" },
];

/**
 * Shared frame for /login and /register. It lives in the (auth) route-group layout, so it stays
 * mounted while navigating between the two pages: the canvas never reloads, the camera just
 * glides to the other view. Layers: gradient backdrop, then the fixed canvas, then the content,
 * whose wrappers ignore the pointer so drags and clicks on empty space reach the scene.
 */
export default function AuthShell({ children }: { children: React.ReactNode }) {
  const { theme, setTheme } = useTheme();
  const pathname = usePathname();
  const view: AuthView = pathname?.startsWith("/register") ? "register" : "login";
  const rootRef = useRef<HTMLDivElement>(null);
  const sceneSignal = useRef<(event: AuthSignal) => void>(() => {});
  const signal = useCallback((event: AuthSignal) => sceneSignal.current(event), []);
  const api = useMemo(() => ({ signal }), [signal]);

  // Chip parallax via CSS variables, so pointer movement never re-renders React.
  useEffect(() => {
    const root = rootRef.current;
    if (!root || prefersReducedMotion()) return;
    let raf = 0;
    let x = 0;
    let y = 0;
    const onMove = (e: PointerEvent) => {
      x = (e.clientX / window.innerWidth) * 2 - 1;
      y = (e.clientY / window.innerHeight) * 2 - 1;
      if (raf) return;
      raf = requestAnimationFrame(() => {
        raf = 0;
        root.style.setProperty("--auth-px", x.toFixed(3));
        root.style.setProperty("--auth-py", y.toFixed(3));
      });
    };
    window.addEventListener("pointermove", onMove, { passive: true });
    return () => {
      window.removeEventListener("pointermove", onMove);
      cancelAnimationFrame(raf);
    };
  }, []);

  const toggleButton = (name: "cream" | "hud", label: string) => (
    <button
      type="button"
      aria-pressed={theme === name}
      onClick={() => theme !== name && setTheme(name)}
      className={`px-2.5 py-1 rounded-md text-[10px] font-bold uppercase tracking-wider transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-1 focus-visible:outline-brass-500 ${
        theme === name ? "bg-brass-600 text-white" : "text-stone-600 hover:text-ink"
      }`}
    >
      {label}
    </button>
  );

  return (
    <AuthSceneContext.Provider value={api}>
      <div ref={rootRef} className="relative min-h-[100dvh] overflow-x-hidden">
        <div aria-hidden="true" className="auth-backdrop fixed inset-0" />
        <AuthScene theme={theme} view={view} signalRef={sceneSignal} />

        <div className="relative z-10 min-h-[100dvh] flex flex-col pointer-events-none">
          <header className="flex items-center justify-end px-4 sm:px-6 lg:px-12 pt-4 sm:pt-5">
            <div
              role="group"
              aria-label="Theme"
              className="pointer-events-auto flex items-center gap-0.5 p-0.5 rounded-lg bg-cream-50/80 border border-cream-300 backdrop-blur-sm shadow-sm"
            >
              {toggleButton("cream", "Cream")}
              {toggleButton("hud", "HUD")}
            </div>
          </header>

          <main className="flex-1 w-full max-w-[1400px] mx-auto px-4 sm:px-6 lg:px-12 xl:px-20 py-6 lg:py-10 flex flex-col lg:flex-row items-center justify-center lg:justify-between gap-6 lg:gap-10">
            {/* Hero (lg+ only) */}
            <section className="auth-hero hidden lg:flex flex-col max-w-xl">
              <p className="text-[11px] font-semibold uppercase tracking-[0.24em] text-brass-700">Multi-Model Agentic RAG</p>
              <p className="font-heading font-serif text-5xl xl:text-6xl font-semibold leading-[1.06] tracking-tight text-ink mt-5">
                Answers you can trace back to the source.
              </p>
              <p className="mt-5 text-[17px] leading-relaxed text-stone-600 max-w-md">
                Ask your documents, the web and your images, with every answer checked against its sources.
              </p>
              <ul className="mt-10 flex flex-col gap-3.5" aria-label="Highlights">
                {FEATURES.map((f) => (
                  <li
                    key={f.label}
                    className={`auth-chip pointer-events-auto self-start ${f.indent}`}
                    style={{ "--auth-depth": f.depth } as React.CSSProperties}
                  >
                    <span
                      className="auth-chip-float inline-flex items-center gap-2.5 px-4 py-2 rounded-full bg-white/70 border border-cream-300 backdrop-blur-md shadow-sm text-[13px] font-semibold text-ink transition-colors hover:border-brass-400"
                      style={{ "--auth-delay": f.delay } as React.CSSProperties}
                    >
                      <svg viewBox="0 0 12 12" className="w-2.5 h-2.5 text-brass-500" aria-hidden="true">
                        <path d="M6 0.8 11.2 6 6 11.2 0.8 6Z" fill="currentColor" />
                      </svg>
                      {f.label}
                    </span>
                  </li>
                ))}
              </ul>
            </section>

            {/* Small screens: the hero collapses to one line above the card. */}
            <p className="lg:hidden flex items-center gap-2 text-[12px] font-semibold uppercase tracking-[0.18em] text-brass-700">
              <PraxisMark className="w-4 h-4" />
              Praxis · Multi-model agentic RAG
            </p>

            <div className="w-full max-w-[440px] pointer-events-auto">{children}</div>
          </main>
        </div>
      </div>
    </AuthSceneContext.Provider>
  );
}
