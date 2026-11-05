import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
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
import { cn } from "@onyx/ui/lib/utils";
import { FileText } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import {
  euro,
  type QuoteStatus,
  quotationsPath,
  STATUS_LABEL,
  STATUS_VARIANT,
} from "@/lib/quotations";
import { workspaceWith } from "@/lib/settings-guard";

import { SELECT_CLASS } from "../../../settings/form-status";
import { ListToolbar, Pager } from "../../crm/_components/list-controls";
import { param, type SearchParams } from "../../crm/data";

const LINK = "font-medium underline-offset-4 hover:underline";

export default async function QuotesPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = quotationsPath(slug, "quotes");
  const workspace = await workspaceWith(slug, "quotations.read", path);
  const search = await searchParams;
  const q = param(search.q, 100);
  const cursor = param(search.cursor);
  const statusParam = param(search.status);
  const status =
    statusParam && statusParam in STATUS_LABEL ? (statusParam as QuoteStatus) : undefined;
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/quotations/quotes", {
        params: { path: { slug }, query: { q, status, cursor } },
      }),
    ),
    path,
  );
  const canWrite = workspace.permissions.includes("quotations.write");

  return (
    <section className="flex flex-col gap-4" aria-labelledby="quotes-heading">
      <h2 id="quotes-heading" className="text-lg font-medium">
        Quotes
      </h2>
      <ListToolbar
        action={path}
        q={q}
        label="Search number or title"
        extra={
          <div className="flex flex-col gap-1">
            <label htmlFor="status" className="text-sm font-medium">
              Status
            </label>
            <select
              id="status"
              name="status"
              defaultValue={status ?? ""}
              className={cn(SELECT_CLASS, "w-40")}
            >
              <option value="">Any status</option>
              {(Object.keys(STATUS_LABEL) as QuoteStatus[]).map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABEL[s]}
                </option>
              ))}
            </select>
          </div>
        }
      >
        {canWrite ? (
          <Button asChild>
            <Link href={quotationsPath(slug, "quotes", "new")}>New quote</Link>
          </Button>
        ) : null}
      </ListToolbar>
      {page.items.length === 0 ? (
        <EmptyState
          icon={FileText}
          title={q || status ? "No matching quotes" : "No quotes yet"}
          description={canWrite && !q ? "Draft a quote for a CRM contact." : undefined}
        />
      ) : (
        <Table>
          <TableCaption className="sr-only">Quotes</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Number</TableHead>
              <TableHead>Title</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Total</TableHead>
              <TableHead>Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((quote) => (
              <TableRow key={quote.id}>
                <TableCell>
                  <Link className={LINK} href={quotationsPath(slug, "quotes", quote.id)}>
                    {quote.number}
                  </Link>
                  {quote.current_version > 1 ? (
                    <span className="text-muted-foreground text-xs"> v{quote.current_version}</span>
                  ) : null}
                </TableCell>
                <TableCell>{quote.title}</TableCell>
                <TableCell>{quote.contact.label}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[quote.status]}>{STATUS_LABEL[quote.status]}</Badge>
                </TableCell>
                <TableCell className="text-right">{euro(quote.gross.amount)}</TableCell>
                <TableCell>
                  <time dateTime={quote.updated_at}>
                    {formatInZone(quote.updated_at, workspace.timezone)}
                  </time>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Pager base={path} params={{ q, status }} cursor={cursor} nextCursor={page.next_cursor} />
    </section>
  );
}
