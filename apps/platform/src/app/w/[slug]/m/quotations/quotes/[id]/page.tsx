import { Badge } from "@onyx/ui/components/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableFooter,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";
import Link from "next/link";
import { Button } from "@onyx/ui/components/button";
import { FileText } from "lucide-react";

import { RecordHeader, RecordLayout } from "@/components/record";

import { withApi } from "@/lib/api-client";
import { crmPath, formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import {
  euro,
  pdfPath,
  quotationsPath,
  type QuoteWarning,
  STATUS_LABEL,
  STATUS_VARIANT,
} from "@/lib/quotations";
import { workspaceWith } from "@/lib/settings-guard";

import { param, recordId, type SearchParams } from "../../../crm/data";
import {
  AddCustomLineForm,
  AddSkuForm,
  ApproveForm,
  LineControls,
  QuoteActions,
  QuoteHeaderForm,
} from "../../_components/forms";

export default async function QuotePage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string; id: string }>;
  searchParams: SearchParams;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = quotationsPath(slug, "quotes", id);
  const workspace = await workspaceWith(slug, "quotations.read", path);
  const versionParam = Number(param((await searchParams).version));
  const version = Number.isInteger(versionParam) && versionParam > 0 ? versionParam : undefined;
  const result = version
    ? await withApi((api) =>
        api.GET("/v1/w/{slug}/quotations/quotes/{quote_id}/versions/{version}", {
          params: { path: { slug, quote_id: id, version } },
        }),
      )
    : await withApi((api) =>
        api.GET("/v1/w/{slug}/quotations/quotes/{quote_id}", {
          params: { path: { slug, quote_id: id } },
        }),
      );
  const quote = requireOk(result, path);
  const perms = workspace.permissions;
  const editable = quote.allowed_actions.includes("edit") && perms.includes("quotations.write");
  const canApprove =
    quote.allowed_actions.includes("approve") && perms.includes("quotations.approve");
  const canAct = perms.includes("quotations.write");
  const vatRates = editable
    ? requireOk(
        await withApi((api) =>
          api.GET("/v1/w/{slug}/catalogue/vat-rates", { params: { path: { slug } } }),
        ),
        path,
      ).items.map((v) => ({ id: v.id, label: `${v.code} ${v.rate_percent}%` }))
    : [];
  const warningsFor = (lineId: string): QuoteWarning[] =>
    quote.warnings.filter((w) => w.line_id === lineId);
  const zone = workspace.timezone;
  const amount = (line: (typeof quote.lines)[number]) =>
    euro(quote.prices_include_vat ? line.gross.amount : line.net.amount);

  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: quotationsPath(slug, "quotes"), label: "Back to quotes" }}
        title={
          <>
            <span className="text-muted-foreground">{quote.number} · </span>
            {quote.title}
          </>
        }
        badges={<Badge variant={STATUS_VARIANT[quote.status]}>{STATUS_LABEL[quote.status]}</Badge>}
        meta={
          <>
            <span>
              Version {quote.version} ({quote.version_status})
            </span>
            <Link
              className="text-brand underline-offset-4 hover:underline"
              href={crmPath(slug, "contacts", quote.contact.id)}
            >
              {quote.contact.label}
            </Link>
            {quote.customer ? <span>{quote.customer.label}</span> : null}
            {quote.lead ? (
              <Link
                className="text-brand underline-offset-4 hover:underline"
                href={crmPath(slug, "leads", quote.lead.id)}
              >
                Lead: {quote.lead.label}
              </Link>
            ) : null}
            <span>
              {quote.price_list.label}, prices {quote.prices_include_vat ? "include" : "exclude"}{" "}
              VAT
            </span>
          </>
        }
        actions={
          <Button asChild variant="outline" size="sm">
            <a href={pdfPath(slug, quote.id, quote.version)} target="_blank" rel="noopener">
              <FileText aria-hidden />
              Open PDF preview (version {quote.version})
            </a>
          </Button>
        }
      />
      <p
        className={
          quote.approved_at
            ? "border-success/25 bg-success/[0.06] rounded-xl border px-4 py-3 text-sm"
            : "text-muted-foreground rounded-xl border border-dashed px-4 py-3 text-sm"
        }
      >
        {quote.approved_at ? (
          <>
            Approved by {quote.approved_by?.label ?? "a former member"} on{" "}
            {formatInZone(quote.approved_at, zone)}
            {quote.valid_until ? ` · valid until ${quote.valid_until}` : ""}
          </>
        ) : (
          "Not approved yet."
        )}
        {quote.outcome_reason ? ` · Reason: ${quote.outcome_reason}` : ""}
      </p>

      <Table>
        <TableCaption className="sr-only">Lines of {quote.number}</TableCaption>
        <TableHeader>
          <TableRow>
            <TableHead>SKU</TableHead>
            <TableHead>Description</TableHead>
            <TableHead className="text-right">Qty</TableHead>
            <TableHead className="text-right">Unit</TableHead>
            <TableHead className="text-right">Disc.</TableHead>
            <TableHead>VAT</TableHead>
            <TableHead className="text-right">Total</TableHead>
            {editable ? (
              <TableHead>
                <span className="sr-only">Edit</span>
              </TableHead>
            ) : null}
          </TableRow>
        </TableHeader>
        <TableBody>
          {quote.lines.map((line) => (
            <TableRow key={line.id}>
              <TableCell className="font-mono text-xs">{line.sku ?? "—"}</TableCell>
              <TableCell>
                <div>{line.description}</div>
                {warningsFor(line.id).map((w) => (
                  <Badge
                    key={w.code}
                    variant={w.blocking ? "destructive" : "warning"}
                    className="mt-1 mr-1"
                  >
                    {w.message}
                  </Badge>
                ))}
              </TableCell>
              <TableCell className="text-right">{line.quantity}</TableCell>
              <TableCell className="text-right">{euro(line.unit_price.amount)}</TableCell>
              <TableCell className="text-right">
                {Number(line.discount_percent) ? `${line.discount_percent}%` : ""}
              </TableCell>
              <TableCell>
                {line.vat_code} {line.vat_percent}%
              </TableCell>
              <TableCell className="text-right">{amount(line)}</TableCell>
              {editable ? (
                <TableCell>
                  <LineControls
                    slug={slug}
                    quoteId={quote.id}
                    line={line}
                    warnings={warningsFor(line.id)}
                  />
                </TableCell>
              ) : null}
            </TableRow>
          ))}
        </TableBody>
        <TableFooter>
          {Number(quote.totals.discount.minor) ? (
            <TableRow>
              <TableCell colSpan={6}>Discount</TableCell>
              <TableCell className="text-right">-{euro(quote.totals.discount.amount)}</TableCell>
              {editable ? <TableCell /> : null}
            </TableRow>
          ) : null}
          <TableRow>
            <TableCell colSpan={6}>Net</TableCell>
            <TableCell className="text-right">{euro(quote.totals.net.amount)}</TableCell>
            {editable ? <TableCell /> : null}
          </TableRow>
          {quote.totals.vat_breakdown.map((group) => (
            <TableRow key={`${group.code}-${group.rate_percent}`}>
              <TableCell colSpan={6}>
                VAT {group.code} {group.rate_percent}%
              </TableCell>
              <TableCell className="text-right">{euro(group.vat.amount)}</TableCell>
              {editable ? <TableCell /> : null}
            </TableRow>
          ))}
          <TableRow>
            <TableCell colSpan={6} className="font-medium">
              Total (EUR)
            </TableCell>
            <TableCell className="text-right font-medium" data-testid="quote-total">
              {euro(quote.totals.gross.amount)}
            </TableCell>
            {editable ? <TableCell /> : null}
          </TableRow>
        </TableFooter>
      </Table>

      <RecordLayout
        main={
          <>
            {editable ? (
              <section
                className="bg-card flex flex-col gap-4 rounded-2xl border p-5"
                aria-labelledby="add-heading"
              >
                <h3 id="add-heading" className="text-sm font-medium">
                  Add lines
                </h3>
                <AddSkuForm slug={slug} quoteId={quote.id} />
                {vatRates.length > 0 ? (
                  <AddCustomLineForm slug={slug} quoteId={quote.id} vatRates={vatRates} />
                ) : null}
                <p className="text-muted-foreground text-xs">
                  Members can give discounts up to {quote.max_discount_percent}%.
                </p>
                <QuoteHeaderForm slug={slug} quote={quote} />
              </section>
            ) : quote.notes ? (
              <p className="text-sm whitespace-pre-wrap">{quote.notes}</p>
            ) : null}
          </>
        }
        aside={
          <>
            {canApprove || canAct ? (
              <section
                className="bg-card flex flex-col gap-4 rounded-2xl border p-5"
                aria-label="Quote actions"
              >
                {canApprove ? <ApproveForm slug={slug} quote={quote} /> : null}
                {canAct ? <QuoteActions slug={slug} quote={quote} /> : null}
              </section>
            ) : null}

            <section
              className="bg-card flex flex-col gap-3 rounded-2xl border p-5"
              aria-labelledby="versions-heading"
            >
              <h3 id="versions-heading" className="text-sm font-medium">
                Versions
              </h3>
              <ul className="flex flex-col gap-1 text-sm">
                {quote.versions.map((v) => (
                  <li key={v.version}>
                    <Link
                      className="text-brand underline-offset-4 hover:underline"
                      href={`${quotationsPath(slug, "quotes", quote.id)}?version=${v.version}`}
                      aria-current={v.version === quote.version ? "page" : undefined}
                    >
                      Version {v.version}
                    </Link>{" "}
                    · {v.status}
                    {v.gross ? ` · ${euro(v.gross.amount)}` : ""}
                    {v.approved_at ? ` · approved ${formatInZone(v.approved_at, zone)}` : ""}
                  </li>
                ))}
              </ul>
            </section>
          </>
        }
      />
    </div>
  );
}
