import { redirect } from "next/navigation";

import { quotationsPath } from "@/lib/quotations";

export default async function QuotationsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(quotationsPath(slug, "quotes"));
}
