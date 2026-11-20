import { Badge } from "@onyx/ui/components/badge";
import Link from "next/link";

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

  return (
    <div className="flex flex-col gap-6">
      <Link className="text-sm underline" href={automotivePath(slug, "vehicles")}>
        Back to vehicles
      </Link>
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-medium">{v.title}</h2>
        <p className="flex flex-wrap items-center gap-2 text-sm">
          <span className="font-medium tabular-nums">{euros(v.price_cents)}</span>
          <Badge variant={VEHICLE_STATUS_VARIANT[v.status]}>{VEHICLE_STATUS_LABEL[v.status]}</Badge>
          {v.listing_url ? (
            <a className="underline" href={v.listing_url} target="_blank" rel="noreferrer">
              View on the website
            </a>
          ) : null}
        </p>
      </div>
      {v.photos.length > 0 ? (
        <ul className="grid grid-cols-2 gap-2 sm:grid-cols-4" aria-label="Photos">
          {v.photos.map((src, i) => (
            <li key={src}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img
                src={src}
                alt={`Photo ${i + 1}`}
                loading="lazy"
                className="bg-muted aspect-[4/3] w-full rounded object-cover"
              />
            </li>
          ))}
        </ul>
      ) : null}
      <dl className="grid max-w-2xl grid-cols-[10rem_1fr] gap-x-4 gap-y-2 text-sm">
        {rows.map(([label, value]) => (
          <div key={label} className="contents">
            <dt className="text-muted-foreground">{label}</dt>
            <dd>{value ?? "—"}</dd>
          </div>
        ))}
      </dl>
      {v.features.length > 0 ? (
        <section aria-labelledby="features-heading" className="flex flex-col gap-2">
          <h3 id="features-heading" className="font-medium">
            Features
          </h3>
          <p className="text-sm">{v.features.join(", ")}</p>
        </section>
      ) : null}
      <p className="text-muted-foreground text-xs">
        Imported from the website. Last updated{" "}
        <time dateTime={v.updated_at}>{formatInZone(v.updated_at, workspace.timezone)}</time>. Empty
        fields were not on the listing.
      </p>
    </div>
  );
}
