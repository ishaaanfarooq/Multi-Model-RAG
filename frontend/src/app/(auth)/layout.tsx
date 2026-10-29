// Shared layout for /login and /register. A route-group layout persists across navigation
// between its pages, so the 3D scene in AuthShell stays mounted when switching between them.
import "./auth.css";
import AuthShell from "@/components/auth/AuthShell";

export default function AuthLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <AuthShell>{children}</AuthShell>;
}
