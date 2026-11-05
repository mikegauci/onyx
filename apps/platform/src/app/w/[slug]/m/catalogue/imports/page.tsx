import { EmptyState } from "@onyx/ui/components/states";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";
import { History } from "lucide-react";

import { withApi } from "@/lib/api-client";
import { cataloguePath } from "@/lib/catalogue";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { Pager } from "../../crm/_components/list-controls";
import { param, type SearchParams } from "../../crm/data";

function count(counts: Record<string, unknown>, key: string): number {
  const value = counts[key];
  return typeof value === "number" ? value : 0;
}

export default async function ImportHistoryPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = cataloguePath(slug, "imports");
  const workspace = await workspaceWith(slug, "catalogue.read", path);
  const cursor = param((await searchParams).cursor);
  const [runs, lists] = await Promise.all([
    withApi((api) =>
      api.GET("/v1/w/{slug}/catalogue/imports", {
        params: { path: { slug }, query: { cursor } },
      }),
    ),
    withApi((api) => api.GET("/v1/w/{slug}/catalogue/price-lists", { params: { path: { slug } } })),
  ]);
  const page = requireOk(runs, path);
  const listCode = new Map(requireOk(lists, path).items.map((pl) => [pl.id, pl.code]));
  const format = (iso: string) => formatInZone(iso, workspace.timezone);

  return (
    <section className="flex flex-col gap-4" aria-labelledby="imports-heading">
      <h2 id="imports-heading" className="text-lg font-medium">
        Import history
      </h2>
      {page.items.length === 0 ? (
        <EmptyState icon={History} title="No imports yet" />
      ) : (
        <Table>
          <TableCaption className="sr-only">Catalogue imports</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Imported</TableHead>
              <TableHead>File</TableHead>
              <TableHead>Exported at source</TableHead>
              <TableHead>Price list</TableHead>
              <TableHead>Changes</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((run) => (
              <TableRow key={run.id}>
                <TableCell>{format(run.created_at)}</TableCell>
                <TableCell>
                  <div className="flex flex-col">
                    <span>{run.filename ?? "Unnamed file"}</span>
                    <span
                      className="text-muted-foreground font-mono text-xs"
                      title="SHA-256 of the file"
                    >
                      {run.file_sha256.slice(0, 12)}
                    </span>
                  </div>
                </TableCell>
                <TableCell>
                  {run.source_exported_at ? format(run.source_exported_at) : "Not given"}
                </TableCell>
                <TableCell>
                  {run.price_list_id ? (listCode.get(run.price_list_id) ?? "—") : "None"}
                </TableCell>
                <TableCell className="text-xs">
                  {count(run.counts, "variants_created")} new SKUs ·{" "}
                  {count(run.counts, "variants_updated")} updated ·{" "}
                  {count(run.counts, "prices_recorded")} prices ·{" "}
                  {count(run.counts, "stock_recorded")} stock · {count(run.counts, "errors")} errors
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Pager base={path} params={{}} cursor={cursor} nextCursor={page.next_cursor} />
    </section>
  );
}
