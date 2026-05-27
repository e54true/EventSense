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
      <body className="min-h-full flex flex-col font-sans text-slate-900">
        <QueryProvider>
          <header className="sticky top-0 z-10 border-b border-slate-200/80 bg-white/80 backdrop-blur">
            <div className="mx-auto max-w-5xl px-6 py-4 flex items-center justify-between">
              <Link
                href="/"
                className="flex items-center gap-2 text-base font-semibold text-slate-900"
              >
                <span className="inline-flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-indigo-500 to-pink-500 text-white text-xs font-bold shadow-sm">
                  ES
                </span>
                EventSense
              </Link>
              <nav className="flex items-center gap-5 text-sm text-slate-600">
                <Link href="/" className="hover:text-slate-900 transition-colors">
                  Timeline
                </Link>
                <Link
                  href="/dashboard"
                  className="hover:text-slate-900 transition-colors"
                >
                  Dashboard
                </Link>
                <span className="hidden sm:inline text-xs text-slate-400">
                  events&nbsp;→&nbsp;LLM&nbsp;predictions&nbsp;→&nbsp;outcomes
                </span>
              </nav>
            </div>
          </header>
          <main className="mx-auto max-w-5xl w-full px-6 py-8 flex-1">
            {children}
          </main>
          <footer className="border-t border-slate-200/80 bg-white/40">
            <div className="mx-auto max-w-5xl px-6 py-4 text-xs text-slate-500 flex justify-between">
              <span>EventSense · M7 prototype</span>
              <span className="font-mono">localhost:3000 → :8000</span>
            </div>
          </footer>
        </QueryProvider>
      </body>
    </html>
  );
}
