"use client";

import { useEffect, useRef, useState } from "react";
import type { ThemeName } from "@/lib/theme";

// Fog palettes per theme. Cream = warm brass/parchment; HUD = neon cyan on black.
const PALETTES: Record<ThemeName, Record<string, number>> = {
  cream: {
    highlightColor: 0xd4ad68, // brass-300
    midtoneColor: 0xa97a3a, // brass-500
    lowlightColor: 0xf0e8d6, // cream-200
    baseColor: 0xf7f2e7, // cream-100 (page bg)
  },
  hud: {
    highlightColor: 0x08c0d0, // neon cyan
    midtoneColor: 0x0f5563, // deep teal
    lowlightColor: 0x0a1622, // dark blue
    baseColor: 0x0a0d11, // page bg (near black)
  },
};

/**
 * Animated ambient backdrop (Vanta FOG), tinted to the active theme. It sits behind
 * the opaque content card, so it adds motion without competing with text for legibility.
 * Well-behaved by design: loaded lazily client-only, skipped under prefers-reduced-motion,
 * torn down while the tab is hidden (so it isn't burning GPU next to local LLM inference),
 * and it re-tints when the theme changes.
 */
export default function VantaBackground({ theme }: { theme: ThemeName }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const effectRef = useRef<{ destroy: () => void; setOptions: (o: Record<string, unknown>) => void } | null>(null);
  const [enabled, setEnabled] = useState(true);

  useEffect(() => {
    const reduced = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setEnabled(false);
      return;
    }

    let cancelled = false;

    (async () => {
      try {
        const [{ default: FOG }, THREE] = await Promise.all([
          import("vanta/dist/vanta.fog.min"),
          import("three"),
        ]);
        if (cancelled || !containerRef.current) return;

        effectRef.current = FOG({
          el: containerRef.current,
          THREE,
          mouseControls: true,
          touchControls: true,
          gyroControls: false,
          minHeight: 200.0,
          minWidth: 200.0,
          blurFactor: 0.62,
          speed: 0.9,
          zoom: 0.75,
          ...PALETTES[theme],
        });
      } catch (err) {
        // WebGL unavailable (software rendering, old driver) — fall back to the
        // static dot texture rather than breaking the page.
        console.warn("Vanta background unavailable:", err);
        if (!cancelled) setEnabled(false);
      }
    })();

    const onVisibility = () => {
      if (document.hidden) {
        effectRef.current?.destroy();
        effectRef.current = null;
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisibility);
      effectRef.current?.destroy();
      effectRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Re-tint live when the theme changes, without tearing down the whole effect.
  useEffect(() => {
    effectRef.current?.setOptions(PALETTES[theme]);
  }, [theme]);

  return (
    <>
      <div
        ref={containerRef}
        aria-hidden
        // Held at partial opacity so the fog stays an ambient wash rather than
        // dominating the page.
        className={`absolute inset-0 pointer-events-none transition-opacity duration-1000 ${
          enabled ? "opacity-[0.55]" : "opacity-0"
        }`}
      />
      {/* Dot texture layered on top — themes via the cream-400 variable. */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.35] bg-[radial-gradient(rgb(var(--cream-400))_1px,transparent_1px)] [background-size:26px_26px]" />
    </>
  );
}
