import { Badge } from "@onyx/ui/components/badge";
import { Input } from "@onyx/ui/components/input";
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
import { Package } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import { cataloguePath } from "@/lib/catalogue";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ListToolbar, Pager } from "../../crm/_components/list-controls";
import { param, type SearchParams } from "../../crm/data";

const LINK = "font-medium underline-offset-4 hover:underline";

export default async function ProductsPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = cataloguePath(slug, "products");
  const workspace = await workspaceWith(slug, "catalogue.read", path);
  const search = await searchParams;
  const q = param(search.q, 100);
  const category = param(search.category, 100);
  const cursor = param(search.cursor);
  const includeArchived = param(search.include_archived) === "true";
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/catalogue/products", {
        params: {
          path: { slug },
          query: { q, category, cursor, include_archived: includeArchived },
        },
      }),
    ),
    path,
  );
  const canImport = workspace.permissions.includes("catalogue.import");

  return (
    <section className="flex flex-col gap-4" aria-labelledby="products-heading">
      <h2 id="products-heading" className="text-lg font-medium">
        Products
      </h2>
      <ListToolbar
        action={path}
        q={q}
        label="Search name, code, brand or SKU"
        extra={
          <>
            <div className="flex flex-col gap-1">
              <label htmlFor="category" className="text-sm font-medium">
                Category
              </label>
              <Input
                id="category"
                name="category"
                defaultValue={category}
                maxLength={100}
                className="w-40"
              />
            </div>
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                name="include_archived"
                value="true"
                defaultChecked={includeArchived}
              />
              Include archived
            </label>
          </>
        }
      />
      {page.items.length === 0 ? (
        <EmptyState
          icon={Package}
          title={q || category ? "No matching products" : "No products yet"}
          description={
            canImport && !q && !category
              ? "Import a catalogue CSV to add products, SKUs, prices and stock."
              : undefined
          }
          action={
            canImport && !q && !category ? (
              <Link className="text-sm underline" href={cataloguePath(slug, "import")}>
                Import a catalogue
              </Link>
            ) : undefined
          }
        />
      ) : (
        <Table>
          <TableCaption className="sr-only">Products</TableCaption>
          <TableHeader>
            <TableRow>
              <TableHead>Product</TableHead>
              <TableHead>Code</TableHead>
              <TableHead>Brand</TableHead>
              <TableHead>Category</TableHead>
              <TableHead>VAT</TableHead>
              <TableHead className="text-right">SKUs</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {page.items.map((product) => (
              <TableRow key={product.id}>
                <TableCell>
                  <span className="flex items-center gap-2">
                    <Link className={LINK} href={cataloguePath(slug, "products", product.id)}>
                      {product.name}
                    </Link>
                    {product.archived_at ? <Badge variant="outline">Archived</Badge> : null}
                  </span>
                </TableCell>
                <TableCell className="font-mono text-xs">{product.code}</TableCell>
                <TableCell>{product.brand ?? "—"}</TableCell>
                <TableCell>{product.category ?? "—"}</TableCell>
                <TableCell>
                  {product.vat ? (
                    `${product.vat.code} ${product.vat.rate_percent}%`
                  ) : (
                    <Badge variant="warning">VAT not set</Badge>
                  )}
                </TableCell>
                <TableCell className="text-right">{product.variant_count}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <Pager
        base={path}
        params={{ q, category, include_archived: includeArchived ? "true" : undefined }}
        cursor={cursor}
        nextCursor={page.next_cursor}
      />
    </section>
  );
}
