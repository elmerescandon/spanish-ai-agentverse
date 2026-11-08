import type { Metadata } from "next";
import { Geist_Mono, Inter, Libre_Baskerville } from "next/font/google";
import { INTRO_DECISION_SCRIPT } from "@/lib/logo-intro";
import "./globals.css";

const libreBaskerville = Libre_Baskerville({
  variable: "--font-libre-baskerville",
  subsets: ["latin"],
  weight: ["400", "700"],
  style: ["normal", "italic"],
});

const inter = Inter({
  variable: "--font-inter",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "Protocol Gap Agent — Diabetes Pipeline",
  description: "Protocol Gap Analysis & Recommendation System for Clinical Trials",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      className={`${libreBaskerville.variable} ${inter.variable} ${geistMono.variable} h-full antialiased`}
      // The intro script may mark <html> before React hydrates.
      suppressHydrationWarning
    >
      <head>
        <script dangerouslySetInnerHTML={{ __html: INTRO_DECISION_SCRIPT }} />
      </head>
      <body className="min-h-full flex flex-col font-sans">{children}</body>
    </html>
  );
}
