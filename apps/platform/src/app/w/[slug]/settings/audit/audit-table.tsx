"use client";

import type { components } from "@onyx/api-client";
import { type ColumnDef, DataTable } from "@onyx/ui/components/data-table";

type Entry = components["schemas"]["AuditEntryOut"];

export function formatInZone(iso: string, timezone: string): string {
  return new Intl.DateTimeFormat("en-GB", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: timezone,
  }).format(new Date(iso));
}

export function AuditTable({ entries, timezone }: { entries: Entry[]; timezone: string }) {
  const columns: ColumnDef<Entry>[] = [
    {
      accessorKey: "occurred_at",
      header: "When",
      cell: ({ row }) => (
        <time dateTime={row.original.occurred_at} className="whitespace-nowrap tabular-nums">
          {formatInZone(row.original.occurred_at, timezone)}
        </time>
      ),
    },
    {
      id: "actor",
      header: "Who",
      accessorFn: (e) => e.actor?.display_name ?? (e.actor ? "Former member" : "System"),
    },
    {
      accessorKey: "action",
      header: "Action",
      cell: ({ getValue }) => <code>{String(getValue())}</code>,
    },
    {
      id: "target",
      header: "Target",
      enableSorting: false,
      accessorFn: (e) => e.target_type ?? "—",
    },
    {
      accessorKey: "request_id",
      header: "Reference",
      enableSorting: false,
      cell: ({ getValue }) => (
        <span className="text-muted-foreground font-mono text-xs">{String(getValue() ?? "—")}</span>
      ),
    },
  ];
  return (
    <DataTable
      caption="Audit log"
      columns={columns}
      data={entries}
      getRowId={(e) => e.id}
      empty="No audit entries yet."
    />
  );
}
