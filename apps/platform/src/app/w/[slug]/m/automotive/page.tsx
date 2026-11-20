import { redirect } from "next/navigation";

import { automotivePath } from "@/lib/automotive";

export default async function AutomotivePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(automotivePath(slug, "vehicles"));
}
