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
      <body className="min-h-full flex flex-col bg-gray-50">
        <QueryProvider>
          <header className="border-b border-gray-200 bg-white">
            <div className="mx-auto max-w-4xl px-4 py-3 flex items-center justify-between">
              <Link href="/" className="text-lg font-semibold text-gray-900">
                EventSense
              </Link>
              <span className="text-xs text-gray-500">
                events → LLM predictions → outcomes
              </span>
            </div>
          </header>
          <main className="mx-auto max-w-4xl w-full px-4 py-6 flex-1">
            {children}
          </main>
        </QueryProvider>
      </body>
    </html>
  );
}
