import { knowledgePath } from "@/lib/knowledge";
import { workspaceWith } from "@/lib/settings-guard";

import { KnowledgeSearch } from "../_components/search-form";

export default async function KnowledgeSearchPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  await workspaceWith(slug, "knowledge.read", knowledgePath(slug, "search"));
  return (
    <section className="flex flex-col gap-4" aria-labelledby="search-heading">
      <h2 id="search-heading" className="text-lg font-medium">
        Search documents
      </h2>
      <p className="text-muted-foreground text-sm">
        The same search the sales assistant uses. When nothing is relevant enough, it finds nothing
        rather than a weak match.
      </p>
      <KnowledgeSearch slug={slug} />
    </section>
  );
}
