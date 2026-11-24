import { Badge } from "@onyx/ui/components/badge";
import { DetailList } from "@onyx/ui/components/page";

import { BackLink } from "@/components/back-link";
import { RecordLayout } from "@/components/record";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { FORMAT_LABEL, formatSize, knowledgePath, pageLabel } from "@/lib/knowledge";
import { workspaceWith } from "@/lib/settings-guard";

import { DeleteDocumentForm, ReplaceDocumentForm } from "../../_components/forms";

type Props = { params: Promise<{ slug: string; id: string }> };

export default async function DocumentPage({ params }: Props) {
  const { slug, id } = await params;
  const path = knowledgePath(slug, "documents", id);
  const workspace = await workspaceWith(slug, "knowledge.read", path);
  const document = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/knowledge/documents/{document_id}", {
        params: { path: { slug, document_id: id } },
      }),
    ),
    path,
  );
  const canManage = workspace.permissions.includes("knowledge.manage");
  const who = (ref: typeof document.created_by) =>
    ref ? (ref.display_name ?? "A member") : "Former member";

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-6" aria-labelledby="document-heading">
        <BackLink href={knowledgePath(slug, "documents")}>All documents</BackLink>
        <div className="flex flex-wrap items-center gap-3">
          <h2 id="document-heading" className="text-2xl font-light tracking-[-0.02em] text-balance">
            {document.title}
          </h2>
          <Badge variant="secondary">Version {document.version}</Badge>
        </div>
        <div className="bg-card rounded-2xl border p-5">
          <DetailList
            className="lg:grid-cols-3"
            items={[
              {
                label: "File",
                value: (
                  <span className="break-all">
                    {document.filename} ({FORMAT_LABEL[document.format]},{" "}
                    {formatSize(document.size_bytes)})
                  </span>
                ),
              },
              ...(document.page_count != null
                ? [{ label: "Pages", value: document.page_count }]
                : []),
              { label: "Passages", value: document.chunk_count },
              {
                label: "Added",
                value: (
                  <>
                    {who(document.created_by)} ·{" "}
                    <time dateTime={document.created_at}>
                      {formatInZone(document.created_at, workspace.timezone)}
                    </time>
                  </>
                ),
              },
              {
                label: "Updated",
                value: (
                  <>
                    {who(document.updated_by)} ·{" "}
                    <time dateTime={document.updated_at}>
                      {formatInZone(document.updated_at, workspace.timezone)}
                    </time>
                  </>
                ),
              },
            ]}
          />
        </div>
      </section>

      <RecordLayout
        main={
          <section className="flex flex-col gap-3" aria-labelledby="passages-heading">
            <h2 id="passages-heading" className="text-lg font-light tracking-tight">
              Passages
            </h2>
            <p className="text-muted-foreground text-sm">
              The text is split into passages for search. Each shows how it starts.
            </p>
            <ol className="bg-card divide-y rounded-2xl border" aria-label="Passages">
              {document.chunks.map((chunk) => (
                <li key={chunk.ordinal} className="px-5 py-4 text-sm">
                  <p className="text-muted-foreground font-mono text-[11px] tracking-[0.12em] uppercase">
                    Passage {chunk.ordinal + 1}
                    {pageLabel(chunk.page) ? ` · ${pageLabel(chunk.page)}` : ""}
                  </p>
                  <p className="mt-1 whitespace-pre-line">{chunk.excerpt}</p>
                </li>
              ))}
            </ol>
          </section>
        }
        aside={
          canManage ? (
            <>
              <section
                className="bg-card flex flex-col gap-3 rounded-2xl border p-5"
                aria-labelledby="replace-heading"
              >
                <h2 id="replace-heading" className="text-sm font-medium">
                  Replace the file
                </h2>
                <p className="text-muted-foreground text-sm">
                  Upload a newer version. Search switches to it in one step, never a mix of both.
                </p>
                <ReplaceDocumentForm slug={slug} documentId={document.id} title={document.title} />
              </section>
              <section
                className="border-destructive/25 flex flex-col gap-3 rounded-2xl border p-5"
                aria-labelledby="delete-heading"
              >
                <h2 id="delete-heading" className="text-sm font-medium">
                  Delete
                </h2>
                <DeleteDocumentForm slug={slug} documentId={document.id} title={document.title} />
              </section>
            </>
          ) : null
        }
      />
    </div>
  );
}
