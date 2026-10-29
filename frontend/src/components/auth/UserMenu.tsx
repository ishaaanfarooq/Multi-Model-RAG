"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { getSession, logout, onAuthChange, type AuthUser } from "@/lib/auth";

function initials(user: AuthUser): string {
  const words = user.name.trim().split(/\s+/).filter(Boolean);
  const letters = words.length > 1 ? words[0][0] + words[words.length - 1][0] : (words[0] ?? user.email).slice(0, 2);
  return letters.toUpperCase();
}

/** Signed-in user card for the Sidebar footer, styled like the status card above it. */
export default function UserMenu() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    const sync = () => setUser(getSession()?.user ?? null);
    sync();
    return onAuthChange(sync);
  }, []);

  if (!user) return null;

  const signOut = () => {
    logout();
    router.replace("/login");
  };

  return (
    <div className="mt-2.5 p-3 rounded-2xl bg-cream-50 border border-cream-300 flex items-center gap-3">
      <div
        aria-hidden="true"
        className="w-9 h-9 rounded-xl bg-gradient-to-br from-brass-400 to-brass-600 text-white flex items-center justify-center text-[12px] font-bold tracking-wide flex-shrink-0 shadow-sm"
      >
        {initials(user)}
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[13px] font-semibold text-ink leading-tight" title={user.name}>
          {user.name}
        </p>
        <p className="truncate text-[11px] text-stone-500 leading-tight mt-0.5" title={user.email}>
          {user.email}
        </p>
      </div>
      <button
        type="button"
        onClick={signOut}
        title="Sign out"
        aria-label="Sign out"
        className="w-8 h-8 flex items-center justify-center rounded-xl text-stone-500 hover:text-brick-700 hover:bg-brick-50 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brass-500 transition-colors flex-shrink-0"
      >
        <svg className="w-[17px] h-[17px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3" />
          <path d="M10 17l-5-5 5-5" />
          <path d="M5 12h11" />
        </svg>
      </button>
    </div>
  );
}
