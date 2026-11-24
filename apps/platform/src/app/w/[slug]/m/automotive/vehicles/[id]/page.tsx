import { Badge } from "@onyx/ui/components/badge";
import { Button } from "@onyx/ui/components/button";
import { Panel } from "@onyx/ui/components/page";
import { ArrowUpRight } from "lucide-react";

import { RecordHeader, RecordLayout } from "@/components/record";
import { withApi } from "@/lib/api-client";
import {
  automotivePath,
  euros,
  kilometres,
  VEHICLE_STATUS_LABEL,
  VEHICLE_STATUS_VARIANT,
} from "@/lib/automotive";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { recordId } from "../../../crm/data";

export default async function VehiclePage({
  params,
}: {
  params: Promise<{ slug: string; id: string }>;
}) {
  const { slug, id: rawId } = await params;
  const id = recordId(rawId);
  const path = automotivePath(slug, "vehicles", id);
  const workspace = await workspaceWith(slug, "catalogue.read", path);
  const v = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/vehicles/{vehicle_id}", {
        params: { path: { slug, vehicle_id: id } },
      }),
    ),
    path,
  );
  const rows: [string, string | number | null][] = [
    ["Stock number", v.stock_number],
    ["Make", v.make],
    ["Model", v.model],
    ["Year", v.year],
    ["Mileage", v.mileage_km !== null ? kilometres(v.mileage_km) : null],
    ["Engine", v.engine_cc !== null ? `${v.engine_cc} cc` : null],
    ["Fuel", v.fuel],
    ["Transmission", v.transmission],
    ["Body", v.body_type],
    ["Colour", v.colour],
    ["Doors", v.doors],
    ["Condition", v.condition],
  ];

  const [hero, ...rest] = v.photos;
  return (
    <div className="flex flex-col gap-6">
      <RecordHeader
        back={{ href: automotivePath(slug, "vehicles"), label: "Back to vehicles" }}
        title={v.title}
        badges={
          <Badge variant={VEHICLE_STATUS_VARIANT[v.status]}>{VEHICLE_STATUS_LABEL[v.status]}</Badge>
        }
        meta={
          <>
            <span className="text-foreground text-lg font-light tabular-nums">
              {euros(v.price_cents)}
            </span>
            {v.stock_number ? <span>Stock #{v.stock_number}</span> : null}
          </>
        }
        actions={
          v.listing_url ? (
            <Button asChild variant="outline" size="sm">
              <a href={v.listing_url} target="_blank" rel="noreferrer">
                View on the website
                <ArrowUpRight aria-hidden />
              </a>
            </Button>
          ) : null
        }
      />
      <RecordLayout
        main={
          <>
            {hero ? (
              <ul className="grid grid-cols-4 gap-2" aria-label="Photos">
                {[hero, ...rest].map((src, i) => (
                  <li key={src} className={i === 0 ? "col-span-4" : undefined}>
                    {/* eslint-disable-next-line @next/next/no-img-element */}
                    <img
                      src={src}
                      alt={`Photo ${i + 1}`}
                      loading={i === 0 ? "eager" : "lazy"}
                      className={
                        i === 0
                          ? "bg-muted aspect-[16/9] w-full rounded-2xl border object-cover"
                          : "bg-muted aspect-[4/3] w-full rounded-xl border object-cover"
                      }
                    />
                  </li>
                ))}
              </ul>
            ) : null}
            {v.features.length > 0 ? (
              <Panel title="Features" as="h3" divided={false}>
                <ul className="flex flex-wrap gap-2">
                  {v.features.map((feature) => (
                    <li key={feature}>
                      <Badge variant="secondary">{feature}</Badge>
                    </li>
                  ))}
                </ul>
              </Panel>
            ) : null}
          </>
        }
        aside={
          <Panel title="Specification" as="h3" divided={false}>
            <dl className="divide-y text-sm">
              {rows.map(([label, value]) => (
                <div key={label} className="flex justify-between gap-4 py-2 first:pt-0 last:pb-0">
                  <dt className="text-muted-foreground">{label}</dt>
                  <dd className="text-right">{value ?? "—"}</dd>
                </div>
              ))}
            </dl>
            <p className="text-muted-foreground mt-4 border-t pt-4 text-xs">
              Imported from the website. Last updated{" "}
              <time dateTime={v.updated_at}>{formatInZone(v.updated_at, workspace.timezone)}</time>.
              Empty fields were not on the listing.
            </p>
          </Panel>
        }
      />
    </div>
  );
}
