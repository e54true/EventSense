import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Link from "next/link";
import "./globals.css";
import { QueryProvider } from "@/components/QueryProvider";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "EventSense",
  description: "Market event analysis with LLM predictions",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="en"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full flex flex-col font-sans text-term-text">
        <QueryProvider>
          <header className="sticky top-0 z-10 border-b border-term-border bg-[#070b10]/90 backdrop-blur">
            <div className="mx-auto max-w-6xl px-6 py-3 flex items-center justify-between">
              <Link
                href="/"
                className="flex items-center gap-2.5 font-mono text-sm font-bold tracking-[0.25em] text-term-text"
              >
                <span className="inline-flex h-6 w-6 items-center justify-center bg-term-amber text-[#0a0e14] text-[11px] font-black tracking-normal">
                  ES
                </span>
                EVENTSENSE
              </Link>
              <nav className="flex items-center gap-6 font-mono text-xs tracking-widest text-term-muted">
                <Link
                  href="/"
                  className="hover:text-term-amber transition-colors"
                >
                  TIMELINE
                </Link>
                <Link
                  href="/dashboard"
                  className="hover:text-term-amber transition-colors"
                >
                  DASHBOARD
                </Link>
                <span className="hidden sm:inline-flex items-center gap-1.5 text-[10px] text-term-dim">
                  <span className="h-1.5 w-1.5 rounded-full bg-term-up animate-pulse" />
                  LIVE
                </span>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-6xl w-full px-6 py-8 flex-1">
            {children}
          </main>
          <footer className="border-t border-term-border bg-[#070b10]/60">
            <div className="mx-auto max-w-6xl px-6 py-3 font-mono text-[11px] text-term-dim flex justify-between">
              <span>EVENTSENSE / M7 PROTOTYPE</span>
              <span>EVENTS → LLM PREDICTIONS → OUTCOMES</span>
            </div>
          </footer>
        </QueryProvider>
      </body>
    </html>
  );
}
