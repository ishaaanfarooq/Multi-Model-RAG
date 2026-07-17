// Root layout for the Praxis frontend application
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Praxis | Agentic RAG Workspace",
  description: "Praxis — a multi-model, multi-agent RAG workspace that retrieves, verifies, and acts on documents, web sources, images, email, and messaging.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="font-sans bg-[var(--color-background)] text-[var(--color-foreground)] antialiased">
        {children}
      </body>
    </html>
  );
}
