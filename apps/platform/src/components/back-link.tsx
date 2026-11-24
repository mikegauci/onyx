import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

/** "Back to …" link above a record page. */
export function BackLink({ href, children }: { href: string; children: ReactNode }) {
  return (
    <Link
      href={href}
      className="text-muted-foreground hover:text-foreground focus-visible:ring-ring inline-flex items-center gap-1.5 self-start rounded-sm text-sm transition-colors focus-visible:ring-2 focus-visible:outline-none"
    >
      <ArrowLeft aria-hidden className="size-4" />
      {children}
    </Link>
  );
}
