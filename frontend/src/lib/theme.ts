"use client";

import { useCallback, useEffect, useState } from "react";

export type ThemeName = "cream" | "hud";

export const THEME_KEY = "mmrag.theme.v1";

function apply(theme: ThemeName) {
  const el = document.documentElement;
  if (theme === "hud") el.dataset.theme = "hud";
  else delete el.dataset.theme; // fall back to :root (Cream)
}

/**
 * Cream (default) vs HUD (dark) theme, persisted to localStorage. The actual palette
 * lives in globals.css keyed off `data-theme` on <html>; this just flips the attribute.
 * A blocking script in layout.tsx applies the saved theme before first paint so there's
 * no flash — this hook keeps React state in sync after hydration.
 */
export function useTheme() {
  const [theme, setTheme] = useState<ThemeName>("cream");

  useEffect(() => {
    const saved = (localStorage.getItem(THEME_KEY) as ThemeName) || "cream";
    setTheme(saved);
    apply(saved);
  }, []);

  const setThemePersisted = useCallback((next: ThemeName) => {
    setTheme(next);
    apply(next);
    try {
      localStorage.setItem(THEME_KEY, next);
    } catch {
      /* ignore */
    }
  }, []);

  const toggle = useCallback(() => {
    setThemePersisted(theme === "cream" ? "hud" : "cream");
  }, [theme, setThemePersisted]);

  return { theme, toggle, setTheme: setThemePersisted };
}
