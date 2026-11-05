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
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import {
  AVAILABILITY_LABEL,
  AVAILABILITY_VARIANT,
  attributeLabel,
  cataloguePath,
  describeSource,
  formatEuro,
  type PriceList,
  type Variant,
} from "@/lib/catalogue";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { recordId } from "../../../crm/data";
import { ArchiveButton } from "../../_components/buttons";

function PriceCell({
  variant,
  priceList,
  format,
}: {
  variant: Variant;
  priceList: PriceList;
  format: (iso: string) => string;
}) {
  const price = variant.prices.find((p) => p.price_list_id === priceList.id);
  if (!price) return <span className="text-muted-foreground">Price not provided</span>;
  return (
    <div className="flex flex-col">
      <span className="font-medium tabular-nums">
        {formatEuro(price.amount)}{" "}
        <span className="text-muted-foreground text-xs font-normal">
          {price.includes_vat ? "incl. VAT" : "excl. VAT"}
        </span>
      </span>
      <span className="text-muted-foreground text-xs">
        Valid from {format(price.valid_from)} · {describeSource(price.source, format)}
      </span>
    </div>
  );
}

function StockCell({ variant, format }: { variant: Variant; format: (iso: string) => string }) {
  return (
    <div className="flex flex-col gap-1">
      <Badge variant={AVAILABILITY_VARIANT[variant.availability]} className="self-start">
        {AVAILABILITY_LABEL[variant.availability]}
      </Badge>
      {variant.stock.map((level) => (
        <span key={level.location} className="text-muted-foreground text-xs">
          {level.location}: {level.quantity_available} as of {format(level.observed_at)} ·{" "}
          {describeSource(level.source, format)}
        </span>
      ))}
    </div>
  );
}

export default async function ProductPage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = cataloguePath(slug, "products", id);
  const workspace = await workspaceWith(slug, "catalogue.read", path);
  const product = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/catalogue/products/{product_id}", {
        params: { path: { slug, product_id: id } },
      }),
    ),
    path,
  );
  const canManage = workspace.permissions.includes("catalogue.manage");
  const format = (iso: string) => formatInZone(iso, workspace.timezone);

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={cataloguePath(slug, "products")}>
        Back to products
      </Link>
      <div className="flex flex-col gap-1">
        <h2 className="text-xl font-medium">{product.name}</h2>
        <p className="text-muted-foreground font-mono text-xs">{product.code}</p>
        {product.archived_at ? (
          <p className="text-muted-foreground text-sm">Archived product</p>
        ) : null}
      </div>
      <dl className="grid max-w-2xl grid-cols-[max-content_1fr] gap-x-6 gap-y-2 text-sm">
        <dt className="text-muted-foreground">Brand</dt>
        <dd>{product.brand ?? "Not provided"}</dd>
        <dt className="text-muted-foreground">Category</dt>
        <dd>{product.category ?? "Not provided"}</dd>
        <dt className="text-muted-foreground">VAT</dt>
        <dd>
          {product.vat ? (
            `${product.vat.name} (${product.vat.code}, ${product.vat.rate_percent}%)`
          ) : (
            <Badge variant="warning">VAT not set</Badge>
          )}
        </dd>
        <dt className="text-muted-foreground">Last import</dt>
        <dd>
          {product.last_import ? describeSource(product.last_import, format) : "Not imported"}
        </dd>
        {product.description ? (
          <>
            <dt className="text-muted-foreground">Description</dt>
            <dd className="whitespace-pre-wrap">{product.description}</dd>
          </>
        ) : null}
      </dl>
      {canManage ? (
        <ArchiveButton slug={slug} kind="product" id={id} archived={!!product.archived_at} />
      ) : null}

      <section className="flex flex-col gap-3" aria-labelledby="skus-heading">
        <h3 id="skus-heading" className="font-medium">
          SKUs
        </h3>
        {product.price_lists.length === 0 ? (
          <p className="text-muted-foreground text-sm">
            No price lists yet, so no prices can be shown.
          </p>
        ) : null}
        <Table>
          <TableCaption className="sr-only">SKUs of {product.name}</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>SKU</TableHead>
              <TableHead>Attributes</TableHead>
              {product.price_lists.map((pl) => (
                <TableHead key={pl.id}>
                  {pl.name} ({pl.code})
                </TableHead>
              ))}
              <TableHead>Stock</TableHead>
              {canManage ? <TableHead>Actions</TableHead> : null}
            </TableRow>
          </TableHeader>
          <TableBody>
            {product.variants.map((variant) => (
              <TableRow key={variant.id}>
                <TableCell className="align-top">
                  <div className="flex flex-col">
                    <span className="font-mono text-xs font-medium">{variant.sku}</span>
                    {variant.name ? <span>{variant.name}</span> : null}
                    {variant.archived_at ? (
                      <Badge variant="outline" className="self-start">
                        Archived
                      </Badge>
                    ) : null}
                  </div>
                </TableCell>
                <TableCell className="align-top text-xs">
                  {Object.keys(variant.attributes).length === 0 ? (
                    <span className="text-muted-foreground">None</span>
                  ) : (
                    <ul>
                      {Object.entries(variant.attributes).map(([name, value]) => (
                        <li key={name}>
                          {attributeLabel(name)}: {value}
                        </li>
                      ))}
                    </ul>
                  )}
                </TableCell>
                {product.price_lists.map((pl) => (
                  <TableCell key={pl.id} className="align-top">
                    <PriceCell variant={variant} priceList={pl} format={format} />
                  </TableCell>
                ))}
                <TableCell className="align-top">
                  <StockCell variant={variant} format={format} />
                </TableCell>
                {canManage ? (
                  <TableCell className="align-top">
                    <ArchiveButton
                      slug={slug}
                      kind="variant"
                      id={variant.id}
                      archived={!!variant.archived_at}
                      name={variant.sku}
                    />
                  </TableCell>
                ) : null}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </section>
    </div>
  );
}
