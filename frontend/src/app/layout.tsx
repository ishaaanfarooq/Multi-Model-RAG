// Root layout for the Multi-Model RAG frontend application - v1.4.3-stable
import type { Metadata } from "next";
import { Inter, Outfit } from "next/font/google";
import "./globals.css";

const inter = Inter({ 
  subsets: ["latin"], 
  variable: "--font-inter",
  weight: ["300", "400", "500", "600", "700"] 
});

const outfit = Outfit({ 
  subsets: ["latin"], 
  variable: "--font-outfit",
  weight: ["400", "500", "600", "700"] 
});

export const metadata: Metadata = {
  title: "Multi-Model RAG | Professional AI Pipeline",
  description: "Cloud-Based Multi-Model Retrieval-Augmented Generation System with real-time pipeline visualization",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className={`${inter.variable} ${outfit.variable} font-sans bg-[var(--color-background)] text-[var(--color-foreground)] antialiased`}>
        {children}
      </body>
    </html>
  );
}
