"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { AuthError, fetchMe, getSession, logout, onAuthChange, type Session } from "@/lib/auth";

// setTimeout stores its delay as a signed 32-bit int; anything longer fires immediately.
const MAX_TIMEOUT_MS = 2 ** 31 - 1;

/**
 * Renders the workspace only for a signed-in user. The first render (server and client alike) is
 * a loader: localStorage is read in an effect, so there is no hydration mismatch and no flash of
 * the app before the redirect. Uses Tailwind tokens only, since auth.css belongs to /login.
 */
export default function AuthGuard({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [session, setSession] = useState<Session | null>(null);
  // Set before a deliberate sign-out, so the onAuthChange listener doesn't redirect a second time.
  const leavingRef = useRef(false);

  useEffect(() => {
    const current = getSession();
    if (!current) {
      router.replace("/login?next=" + encodeURIComponent(window.location.pathname));
      return;
    }
    setSession(current);
  }, [router]);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;

    const expire = () => {
      leavingRef.current = true;
      logout();
      router.replace("/login?expired=1");
    };

    // The token may have been revoked server-side (deleted account, rotated secret). A network
    // error keeps the user signed in: the backend may just be restarting, and the Sidebar
    // already shows "Offline".
    fetchMe().catch((err: unknown) => {
      if (!cancelled && err instanceof AuthError && err.status === 401) expire();
    });

    const timer = window.setTimeout(expire, Math.min(Math.max(session.exp * 1000 - Date.now(), 0), MAX_TIMEOUT_MS));

    // Signed out here (UserMenu) or in another tab.
    const unsubscribe = onAuthChange(() => {
      if (!leavingRef.current && !getSession()) {
        leavingRef.current = true;
        router.replace("/login");
      }
    });

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
      unsubscribe();
    };
  }, [session, router]);

  if (!session) {
    // In-flow rather than position: fixed, so Next's scroll-to-new-page logic has a target.
    return (
      <div
        className="h-screen w-full flex flex-col items-center justify-center gap-4 bg-cream-100"
        role="status"
        aria-live="polite"
      >
        <svg viewBox="0 0 48 48" className="w-12 h-12 text-brass-500 motion-safe:animate-pulse" aria-hidden="true">
          <path d="M24 3 42 13.5v21L24 45 6 34.5v-21Z" fill="none" stroke="currentColor" strokeWidth="2" />
          <path d="M24 13 33 18.5v11L24 35l-9-5.5v-11Z" fill="currentColor" opacity="0.85" />
        </svg>
        <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-stone-600">Checking your session…</span>
      </div>
    );
  }

  return <>{children}</>;
}
