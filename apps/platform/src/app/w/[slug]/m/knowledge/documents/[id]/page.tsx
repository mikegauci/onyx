import Link from "next/link";

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
      <section className="flex flex-col gap-3" aria-labelledby="document-heading">
        <p className="text-sm">
          <Link
            className="underline-offset-4 hover:underline"
            href={knowledgePath(slug, "documents")}
          >
            ← All documents
          </Link>
        </p>
        <h2 id="document-heading" className="text-lg font-medium">
          {document.title}
        </h2>
        <dl className="grid grid-cols-[max-content_1fr] gap-x-4 gap-y-1 text-sm">
          <dt className="text-muted-foreground">File</dt>
          <dd className="break-all">
            {document.filename} ({FORMAT_LABEL[document.format]}, {formatSize(document.size_bytes)})
          </dd>
          {document.page_count != null ? (
            <>
              <dt className="text-muted-foreground">Pages</dt>
              <dd>{document.page_count}</dd>
            </>
          ) : null}
          <dt className="text-muted-foreground">Passages</dt>
          <dd>{document.chunk_count}</dd>
          <dt className="text-muted-foreground">Version</dt>
          <dd>{document.version}</dd>
          <dt className="text-muted-foreground">Added</dt>
          <dd>
            {who(document.created_by)} ·{" "}
            <time dateTime={document.created_at}>
              {formatInZone(document.created_at, workspace.timezone)}
            </time>
          </dd>
          <dt className="text-muted-foreground">Updated</dt>
          <dd>
            {who(document.updated_by)} ·{" "}
            <time dateTime={document.updated_at}>
              {formatInZone(document.updated_at, workspace.timezone)}
            </time>
          </dd>
        </dl>
      </section>

      <section className="flex flex-col gap-3" aria-labelledby="passages-heading">
        <h2 id="passages-heading" className="text-lg font-medium">
          Passages
        </h2>
        <p className="text-muted-foreground text-sm">
          The text is split into passages for search. Each shows how it starts.
        </p>
        <ol className="flex flex-col gap-2" aria-label="Passages">
          {document.chunks.map((chunk) => (
            <li key={chunk.ordinal} className="rounded-md border p-3 text-sm">
              <p className="text-muted-foreground text-xs">
                Passage {chunk.ordinal + 1}
                {pageLabel(chunk.page) ? ` · ${pageLabel(chunk.page)}` : ""}
              </p>
              <p className="mt-1 whitespace-pre-line">{chunk.excerpt}</p>
            </li>
          ))}
        </ol>
      </section>

      {canManage ? (
        <>
          <section className="flex flex-col gap-3" aria-labelledby="replace-heading">
            <h2 id="replace-heading" className="text-lg font-medium">
              Replace the file
            </h2>
            <p className="text-muted-foreground text-sm">
              Upload a newer version. Search switches to it in one step, never a mix of both.
            </p>
            <ReplaceDocumentForm slug={slug} documentId={document.id} title={document.title} />
          </section>
          <section className="flex flex-col gap-3" aria-labelledby="delete-heading">
            <h2 id="delete-heading" className="text-lg font-medium">
              Delete
            </h2>
            <DeleteDocumentForm slug={slug} documentId={document.id} title={document.title} />
          </section>
        </>
      ) : null}
    </div>
  );
}
