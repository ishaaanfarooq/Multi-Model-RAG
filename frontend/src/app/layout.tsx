import type { Metadata } from "next";
import { Inter } from "next/font/google";
import "./globals.css";

const inter = Inter({ subsets: ["latin"], weight: ["300", "400", "500", "600", "700"] });

export const metadata: Metadata = {
  title: "Multi-Model RAG System — Cloud AI Pipeline",
  description: "Cloud-Based Multi-Model Retrieval-Augmented Generation System with real-time pipeline visualization",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className={`${inter.className} bg-[#0a0a0f] text-[#e8e6e3] antialiased`}>
        {children}
      </body>
    </html>
  );
}
