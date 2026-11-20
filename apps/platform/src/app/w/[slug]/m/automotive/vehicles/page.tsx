import { Badge } from "@onyx/ui/components/badge";
import { EmptyState } from "@onyx/ui/components/states";
import { Car } from "lucide-react";
import Link from "next/link";

import { withApi } from "@/lib/api-client";
import {
  automotivePath,
  euros,
  VEHICLE_STATUS_LABEL,
  VEHICLE_STATUS_VARIANT,
  type VehicleStatus,
  vehicleSummary,
} from "@/lib/automotive";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { param, type SearchParams } from "../../crm/data";

const STATUSES: VehicleStatus[] = ["available", "reserved", "sold", "withdrawn"];
const PAGE = 48;

export default async function VehiclesPage({
  params,
  searchParams,
}: {
  params: Promise<{ slug: string }>;
  searchParams: SearchParams;
}) {
  const { slug } = await params;
  const path = automotivePath(slug, "vehicles");
  const workspace = await workspaceWith(slug, "catalogue.read", path);
  const search = await searchParams;
  const q = param(search.q, 100);
  const rawStatus = param(search.status, 20);
  const status = STATUSES.includes(rawStatus as VehicleStatus)
    ? (rawStatus as VehicleStatus)
    : rawStatus === "all"
      ? undefined
      : "available";
  const offset = Math.max(0, Number(param(search.offset, 6)) || 0);
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/vehicles", {
        params: { path: { slug }, query: { q, status, limit: PAGE, offset } },
      }),
    ),
    path,
  );
  const canImport = workspace.permissions.includes("catalogue.import");
  const query = (extra: Record<string, string>) => {
    const qs = new URLSearchParams({ ...(q ? { q } : {}), status: status ?? "all", ...extra });
    return `${path}?${qs.toString()}`;
  };

  return (
    <section className="flex flex-col gap-4" aria-labelledby="vehicles-heading">
      <h2 id="vehicles-heading" className="sr-only">
        Vehicles
      </h2>
      <form action={path} className="flex flex-wrap items-end gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Search
          <input
            name="q"
            defaultValue={q ?? ""}
            placeholder="Make, model or stock number"
            className="border-input bg-background h-9 w-64 rounded-md border px-3 text-sm"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Status
          <select
            name="status"
            defaultValue={status ?? "all"}
            className="border-input bg-background h-9 rounded-md border px-3 text-sm"
          >
            <option value="all">All</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {VEHICLE_STATUS_LABEL[s]}
              </option>
            ))}
          </select>
        </label>
        <button type="submit" className="h-9 rounded-md border px-3 text-sm">
          Show
        </button>
        <span className="text-muted-foreground text-sm">{page.total} vehicles</span>
      </form>

      {page.items.length === 0 ? (
        <EmptyState
          icon={Car}
          title="No vehicles"
          description={
            canImport
              ? "Import your stock from your website under Import from website."
              : "Nothing matches. An admin imports the stock from the website."
          }
        />
      ) : (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" aria-label="Vehicles">
          {page.items.map((v) => (
            <li key={v.id} className="flex flex-col overflow-hidden rounded-md border">
              {v.photos[0] ? (
                // Photos are on the dealer's own site; shown as they are, not proxied.
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={v.photos[0]}
                  alt=""
                  loading="lazy"
                  className="bg-muted aspect-[4/3] w-full object-cover"
                />
              ) : (
                <div className="bg-muted aspect-[4/3] w-full" />
              )}
              <div className="flex flex-col gap-1 p-3">
                <Link
                  className="font-medium underline-offset-4 hover:underline"
                  href={automotivePath(slug, "vehicles", v.id)}
                >
                  {v.title}
                </Link>
                <span className="text-muted-foreground text-sm">{vehicleSummary(v)}</span>
                <span className="flex flex-wrap items-center gap-2 text-sm">
                  <span className="font-medium tabular-nums">{euros(v.price_cents)}</span>
                  <Badge variant={VEHICLE_STATUS_VARIANT[v.status]}>
                    {VEHICLE_STATUS_LABEL[v.status]}
                  </Badge>
                  {v.stock_number ? (
                    <span className="text-muted-foreground text-xs">#{v.stock_number}</span>
                  ) : null}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}
      <nav className="flex gap-3 text-sm" aria-label="Pages">
        {offset > 0 ? (
          <Link className="underline" href={query({ offset: String(Math.max(0, offset - PAGE)) })}>
            Previous
          </Link>
        ) : null}
        {offset + PAGE < page.total ? (
          <Link className="underline" href={query({ offset: String(offset + PAGE) })}>
            Next
          </Link>
        ) : null}
      </nav>
    </section>
  );
}
