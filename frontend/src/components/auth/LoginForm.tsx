"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthError, getSession, login, safeNext } from "@/lib/auth";
import { prefersReducedMotion, useAuthScene } from "@/components/auth/AuthShell";
import TiltCard, { CardHeader } from "@/components/auth/TiltCard";
import AuthField, { SubmitButton } from "@/components/auth/AuthField";
import { emailError, normalizeEmail } from "@/components/auth/validation";

export default function LoginForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { signal } = useAuthScene();
  const rawNext = params.get("next");
  const expired = params.get("expired") === "1";

  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState({ email: false, password: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shakeKey, setShakeKey] = useState(0);

  // Already signed in: go straight to the workspace.
  useEffect(() => {
    if (getSession()) router.replace("/");
  }, [router]);

  const errors = { email: emailError(email), password: password ? null : "Enter your password." };
  const valid = !errors.email && !errors.password;

  const edit = (setter: (v: string) => void) => (value: string) => {
    setter(value);
    setError(null);
    signal("keystroke");
  };

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setTouched({ email: true, password: true });
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    signal("submitting");
    try {
      await login(normalizeEmail(email), password);
      signal("success");
      // Let the camera dive into the core before the workspace replaces the page.
      window.setTimeout(() => router.replace(safeNext(rawNext)), prefersReducedMotion() ? 0 : 700);
    } catch (err) {
      signal("error");
      setError(err instanceof AuthError ? err.message : "Sign-in failed. Please try again.");
      setShakeKey((k) => k + 1);
      setSubmitting(false);
    }
  };

  // The submit button is disabled while the form is invalid, so Enter would do nothing:
  // show what is missing instead.
  const onKeyDown = (e: React.KeyboardEvent<HTMLFormElement>) => {
    if (e.key === "Enter" && !valid && e.target instanceof HTMLInputElement) {
      e.preventDefault();
      setTouched({ email: true, password: true });
    }
  };

  const registerHref = rawNext ? `/register?next=${encodeURIComponent(rawNext)}` : "/register";

  return (
    <TiltCard shakeKey={shakeKey}>
      <CardHeader title="Welcome back" subtitle="Sign in to your agentic RAG workspace." />

      <form noValidate onSubmit={submit} onKeyDown={onKeyDown} className="auth-3d mt-7 flex flex-col gap-4" aria-label="Sign in">
        {expired && !error && (
          <div className="auth-depth-field">
            <p role="status" className="rounded-xl border border-brass-300 bg-brass-50 px-3.5 py-2.5 text-[13px] font-medium text-brass-800">
              Your session expired. Please sign in again.
            </p>
          </div>
        )}

        <AuthField
          id="email"
          label="Email"
          type="email"
          icon="mail"
          index={0}
          autoComplete="email"
          value={email}
          onChange={edit(setEmail)}
          onBlur={() => setTouched((t) => ({ ...t, email: true }))}
          error={touched.email ? errors.email : null}
        />
        <AuthField
          id="password"
          label="Password"
          type="password"
          icon="lock"
          index={1}
          autoComplete="current-password"
          value={password}
          onChange={edit(setPassword)}
          onFocus={() => signal("focusPassword")}
          onBlur={() => {
            signal("blurPassword");
            setTouched((t) => ({ ...t, password: true }));
          }}
          error={touched.password ? errors.password : null}
        />

        <div aria-live="polite" className="auth-depth-field">
          {error && (
            <p className="flex items-start gap-2 rounded-xl border border-brick-100 bg-brick-50 px-3.5 py-2.5 text-[13px] font-medium text-brick-700">
              <svg viewBox="0 0 24 24" className="w-4 h-4 mt-0.5 flex-shrink-0" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <circle cx="12" cy="12" r="9" />
                <path d="M12 7.5v5.5M12 16.5h.01" />
              </svg>
              {error}
            </p>
          )}
        </div>

        <SubmitButton label="Sign in" pendingLabel="Signing in…" pending={submitting} disabled={!valid} index={2} />
      </form>

      <p className="auth-depth-field mt-6 text-center text-[14px] text-stone-600">
        New here?{" "}
        <Link
          href={registerHref}
          className="font-semibold text-brass-700 underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-500 rounded"
        >
          Create an account
        </Link>
      </p>
    </TiltCard>
  );
}
