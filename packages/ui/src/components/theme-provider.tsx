"use client";

import { ThemeProvider as NextThemesProvider } from "next-themes";
import type * as React from "react";

/*
 * Follows the device's light/dark preference by default and remembers an
 * explicit choice in localStorage. Adds the `.dark` class on <html>, which the
 * tokens in globals.css key off. Pair with `suppressHydrationWarning` on <html>.
 */
function ThemeProvider({ children, ...props }: React.ComponentProps<typeof NextThemesProvider>) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange
      {...props}
    >
      {children}
    </NextThemesProvider>
  );
}

export { ThemeProvider };
