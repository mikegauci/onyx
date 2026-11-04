import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ThemeProvider } from "@onyx/ui/components/theme-provider";
import { ThemeToggle } from "@onyx/ui/components/theme-toggle";

import "./globals.css";

export const metadata: Metadata = {
  title: "Onyx Platform",
  description: "Onyx Platform workspace.",
  robots: { index: false, follow: false },
};

export default function RootLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <html
      lang="en"
      className={`${GeistSans.variable} ${GeistMono.variable}`}
      suppressHydrationWarning
    >
      <body className="min-h-screen antialiased">
        <ThemeProvider>
          <ThemeToggle className="fixed top-4 right-4 z-50" />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
