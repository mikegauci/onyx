import { Badge } from "@onyx/ui/components/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";

import { withApi } from "@/lib/api-client";
import { cataloguePath } from "@/lib/catalogue";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ArchiveButton, MakeDefaultButton } from "../_components/buttons";
import { PriceListForm, VatRateForm } from "./forms";

export default async function CatalogueSettingsPage({
  params,
}: {
  params: Promise<{ slug: string }>;
}) {
  const { slug } = await params;
  const path = cataloguePath(slug, "settings");
  await workspaceWith(slug, "catalogue.manage", path);
  const [rates, lists] = await Promise.all([
    withApi((api) =>
      api.GET("/v1/w/{slug}/catalogue/vat-rates", {
        params: { path: { slug }, query: { include_archived: true } },
      }),
    ),
    withApi((api) => api.GET("/v1/w/{slug}/catalogue/price-lists", { params: { path: { slug } } })),
  ]);
  const vatRates = requireOk(rates, path).items;
  const priceLists = requireOk(lists, path).items;

  return (
    <div className="flex flex-col gap-10">
      <section className="flex flex-col gap-4" aria-labelledby="vat-heading">
        <h2 id="vat-heading" className="text-lg font-medium">
          VAT rates
        </h2>
        {vatRates.length > 0 ? (
          <Table>
            <TableCaption className="sr-only">VAT rates</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead className="text-right">Rate</TableHead>
                <TableHead>Actions</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {vatRates.map((rate) => (
                <TableRow key={rate.id}>
                  <TableCell className="font-mono text-xs">
                    {rate.code}{" "}
                    {rate.archived_at ? <Badge variant="outline">Archived</Badge> : null}
                  </TableCell>
                  <TableCell>{rate.name}</TableCell>
                  <TableCell className="text-right tabular-nums">{rate.rate_percent}%</TableCell>
                  <TableCell>
                    <ArchiveButton
                      slug={slug}
                      kind="vat"
                      id={rate.id}
                      archived={!!rate.archived_at}
                      name={rate.code}
                    />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-muted-foreground text-sm">No VAT rates yet.</p>
        )}
        <VatRateForm slug={slug} />
      </section>

      <section className="flex flex-col gap-4" aria-labelledby="price-lists-heading">
        <h2 id="price-lists-heading" className="text-lg font-medium">
          Price lists
        </h2>
        {priceLists.length > 0 ? (
          <Table>
            <TableCaption className="sr-only">Price lists</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Code</TableHead>
                <TableHead>Name</TableHead>
                <TableHead>Currency</TableHead>
                <TableHead>VAT</TableHead>
                <TableHead>Default</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {priceLists.map((pl) => (
                <TableRow key={pl.id}>
                  <TableCell className="font-mono text-xs">{pl.code}</TableCell>
                  <TableCell>{pl.name}</TableCell>
                  <TableCell>{pl.currency}</TableCell>
                  <TableCell>{pl.prices_include_vat ? "Included" : "Excluded"}</TableCell>
                  <TableCell>
                    {pl.is_default ? (
                      <Badge variant="brand">Default</Badge>
                    ) : (
                      <MakeDefaultButton slug={slug} id={pl.id} code={pl.code} />
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ) : (
          <p className="text-muted-foreground text-sm">No price lists yet.</p>
        )}
        <PriceListForm slug={slug} />
      </section>
    </div>
  );
}
