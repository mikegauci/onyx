import { redirect } from "next/navigation";

import { inboxPath } from "@/lib/inbox";

export default async function InboxPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(inboxPath(slug, "conversations"));
}
