import { GeistMono } from "geist/font/mono";
import { GeistSans } from "geist/font/sans";
import type { Metadata } from "next";
import type { ReactNode } from "react";

import { ThemeProvider } from "@onyx/ui/components/theme-provider";
import { Toaster } from "@onyx/ui/components/sonner";
import { TooltipProvider } from "@onyx/ui/components/tooltip";

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
          <TooltipProvider>
            {children}
            <Toaster />
          </TooltipProvider>
        </ThemeProvider>
      </body>
    </html>
  );
}
