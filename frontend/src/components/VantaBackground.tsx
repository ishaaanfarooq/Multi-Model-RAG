"use client";

import { useEffect, useRef, useState } from "react";

/**
 * Animated ambient backdrop (Vanta FOG), tinted to the Praxis brass/cream palette.
 *
 * It sits *behind* the opaque content card, so it adds motion without ever
 * competing with text for legibility. Three things keep it well-behaved:
 *  - loaded lazily on the client only (Vanta touches window/WebGL at import time),
 *  - disabled when the user prefers reduced motion,
 *  - paused while the tab is hidden, so it isn't burning GPU next to local
 *    LLM inference when nobody's looking.
 */
export default function VantaBackground() {
  const containerRef = useRef<HTMLDivElement>(null);
  const effectRef = useRef<{ destroy: () => void } | null>(null);
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
          // Brass / cream palette so the motion reads as warm parchment,
          // not the usual neon Vanta look.
          highlightColor: 0xd4ad68, // brass-300
          midtoneColor: 0xa97a3a, // brass-500
          lowlightColor: 0xf0e8d6, // cream-200
          baseColor: 0xf7f2e7, // cream-100 (page background)
          blurFactor: 0.62,
          speed: 0.9,
          zoom: 0.75,
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
  }, []);

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
      {/* Dot texture stays on top of the fog — it's what gives the surface its
          "engineered paper" feel, and it covers us if WebGL fails. */}
      <div className="absolute inset-0 pointer-events-none opacity-[0.35] bg-[radial-gradient(#D2C3A5_1px,transparent_1px)] [background-size:26px_26px]" />
    </>
  );
}
