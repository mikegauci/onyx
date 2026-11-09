import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { FORMAT_LABEL, formatSize, knowledgePath } from "@/lib/knowledge";
import { workspaceWith } from "@/lib/settings-guard";

import { UploadDocumentForm } from "../_components/forms";

/** The workspace's documents. Only their text is kept; the API owns every limit. */
export default async function DocumentsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = knowledgePath(slug, "documents");
  const workspace = await workspaceWith(slug, "knowledge.read", path);
  const documents = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/knowledge/documents", { params: { path: { slug } } }),
    ),
    path,
  ).items;
  const canManage = workspace.permissions.includes("knowledge.manage");

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4" aria-labelledby="documents-heading">
        <h2 id="documents-heading" className="text-lg font-medium">
          Documents
        </h2>
        <p className="text-muted-foreground text-sm">
          Care and installation guides, terms and policies that staff and the sales assistant can
          search. Only the text is kept, not the original file.
        </p>
        {documents.length === 0 ? (
          <p className="text-sm">
            No documents yet.{canManage ? " Upload one below." : " An admin can upload them."}
          </p>
        ) : (
          <Table>
            <TableCaption className="sr-only">Documents</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Title</TableHead>
                <TableHead>File</TableHead>
                <TableHead className="text-right">Passages</TableHead>
                <TableHead>Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {documents.map((d) => (
                <TableRow key={d.id}>
                  <TableCell className="font-medium">
                    <Link
                      className="underline-offset-4 hover:underline"
                      href={knowledgePath(slug, "documents", d.id)}
                    >
                      {d.title}
                    </Link>
                  </TableCell>
                  <TableCell className="text-sm">
                    <span className="break-all">{d.filename}</span>
                    <span className="text-muted-foreground block text-xs">
                      {FORMAT_LABEL[d.format]} · {formatSize(d.size_bytes)}
                      {d.page_count != null ? ` · ${d.page_count} pages` : ""} · version {d.version}
                    </span>
                  </TableCell>
                  <TableCell className="text-right tabular-nums">{d.chunk_count}</TableCell>
                  <TableCell className="text-sm">
                    {d.updated_by?.display_name ?? (d.updated_by ? "A member" : "Former member")}
                    {" · "}
                    <time dateTime={d.updated_at}>
                      {formatInZone(d.updated_at, workspace.timezone)}
                    </time>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
      {canManage ? (
        <section className="flex flex-col gap-4" aria-labelledby="upload-heading">
          <h2 id="upload-heading" className="text-lg font-medium">
            Upload a document
          </h2>
          <p className="text-muted-foreground text-sm">
            Indexing reads the text and prepares it for search, which uses a little of the
            workspace&apos;s AI budget.
          </p>
          <UploadDocumentForm slug={slug} />
        </section>
      ) : null}
    </div>
  );
}
