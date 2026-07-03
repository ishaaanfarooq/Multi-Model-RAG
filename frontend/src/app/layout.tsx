// Root layout for the Multi-Model RAG frontend application - v1.4.3-stable
import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "MultiModel RAG | Research Workspace",
  description: "A multi-model retrieval-augmented generation workspace for documents, web sources, and images.",
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
