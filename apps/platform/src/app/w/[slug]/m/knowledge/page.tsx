import { redirect } from "next/navigation";

import { knowledgePath } from "@/lib/knowledge";

export default async function KnowledgePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(knowledgePath(slug, "documents"));
}
