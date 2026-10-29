"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { AuthError, getSession, register, safeNext } from "@/lib/auth";
import { prefersReducedMotion, useAuthScene } from "@/components/auth/AuthShell";
import TiltCard, { CardHeader } from "@/components/auth/TiltCard";
import AuthField, { SubmitButton } from "@/components/auth/AuthField";
import PasswordStrength from "@/components/auth/PasswordStrength";
import { emailError, nameError, newPasswordError, normalizeEmail } from "@/components/auth/validation";

type Field = "name" | "email" | "password" | "confirm";

export default function RegisterForm() {
  const router = useRouter();
  const params = useSearchParams();
  const { signal } = useAuthScene();
  const rawNext = params.get("next");

  const [values, setValues] = useState<Record<Field, string>>({ name: "", email: "", password: "", confirm: "" });
  const [touched, setTouched] = useState<Record<Field, boolean>>({ name: false, email: false, password: false, confirm: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shakeKey, setShakeKey] = useState(0);

  // Already signed in: go straight to the workspace.
  useEffect(() => {
    if (getSession()) router.replace("/");
  }, [router]);

  const errors: Record<Field, string | null> = {
    name: nameError(values.name),
    email: emailError(values.email),
    password: newPasswordError(values.password),
    confirm: !values.confirm ? "Confirm your password." : values.confirm !== values.password ? "Passwords don't match." : null,
  };
  const valid = !errors.name && !errors.email && !errors.password && !errors.confirm;
  // Live match check: once something is typed in "confirm", say whether it matches right away.
  const confirmShown = touched.confirm || values.confirm.length > 0;
  const confirmMatches = values.confirm.length > 0 && values.confirm === values.password;

  const set = (field: Field) => (value: string) => {
    setValues((v) => ({ ...v, [field]: value }));
    setError(null);
    signal("keystroke");
  };
  const touch = (field: Field) => () => setTouched((t) => ({ ...t, [field]: true }));
  const touchAll = () => setTouched({ name: true, email: true, password: true, confirm: true });

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    touchAll();
    if (!valid || submitting) return;
    setSubmitting(true);
    setError(null);
    signal("submitting");
    try {
      await register(values.name.trim(), normalizeEmail(values.email), values.password);
      signal("success");
      // Registering signs the user in; dive into the core, then open the workspace.
      window.setTimeout(() => router.replace(safeNext(rawNext)), prefersReducedMotion() ? 0 : 700);
    } catch (err) {
      signal("error");
      setError(err instanceof AuthError ? err.message : "Couldn't create the account. Please try again.");
      setShakeKey((k) => k + 1);
      setSubmitting(false);
    }
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLFormElement>) => {
    if (e.key === "Enter" && !valid && e.target instanceof HTMLInputElement) {
      e.preventDefault();
      touchAll();
    }
  };

  const loginHref = rawNext ? `/login?next=${encodeURIComponent(rawNext)}` : "/login";

  return (
    <TiltCard shakeKey={shakeKey}>
      <CardHeader title="Create your account" subtitle="Start asking your documents, the web and your images." />

      <form noValidate onSubmit={submit} onKeyDown={onKeyDown} className="auth-3d mt-7 flex flex-col gap-4" aria-label="Create account">
        <AuthField
          id="name"
          label="Full name"
          type="text"
          icon="user"
          index={0}
          autoComplete="name"
          value={values.name}
          onChange={set("name")}
          onBlur={touch("name")}
          error={touched.name ? errors.name : null}
        />
        <AuthField
          id="email"
          label="Email"
          type="email"
          icon="mail"
          index={1}
          autoComplete="email"
          value={values.email}
          onChange={set("email")}
          onBlur={touch("email")}
          error={touched.email ? errors.email : null}
        />
        <AuthField
          id="password"
          label="Password"
          type="password"
          icon="lock"
          index={2}
          autoComplete="new-password"
          value={values.password}
          onChange={set("password")}
          onFocus={() => signal("focusPassword")}
          onBlur={() => {
            signal("blurPassword");
            touch("password")();
          }}
          describedBy="password-strength"
          error={touched.password ? errors.password : null}
        />
        <PasswordStrength id="password-strength" password={values.password} />
        <AuthField
          id="confirm"
          label="Confirm password"
          type="password"
          icon="lock"
          index={4}
          autoComplete="new-password"
          value={values.confirm}
          onChange={set("confirm")}
          onFocus={() => signal("focusPassword")}
          onBlur={() => {
            signal("blurPassword");
            touch("confirm")();
          }}
          error={confirmShown && !confirmMatches ? errors.confirm : null}
          note={confirmMatches ? "Passwords match" : null}
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

        <SubmitButton label="Create account" pendingLabel="Creating account…" pending={submitting} disabled={!valid} index={5} />
      </form>

      <p className="auth-depth-field mt-6 text-center text-[14px] text-stone-600">
        Already have an account?{" "}
        <Link
          href={loginHref}
          className="font-semibold text-brass-700 underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brass-500 rounded"
        >
          Sign in
        </Link>
      </p>
    </TiltCard>
  );
}
