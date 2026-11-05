"use client";

import type { components } from "@onyx/api-client";
import { Badge } from "@onyx/ui/components/badge";
import { type ColumnDef, DataTable } from "@onyx/ui/components/data-table";

type Org = components["schemas"]["OrganizationSummary"];

const columns: ColumnDef<Org>[] = [
  { accessorKey: "name", header: "Name" },
  {
    accessorKey: "slug",
    header: "Slug",
    cell: ({ getValue }) => <code className="text-xs">{String(getValue())}</code>,
  },
  {
    accessorKey: "status",
    header: "Status",
    cell: ({ getValue }) => <Badge variant="outline">{String(getValue())}</Badge>,
  },
  {
    accessorKey: "member_count",
    header: "Members",
    cell: ({ getValue }) => <span className="tabular-nums">{String(getValue())}</span>,
  },
  {
    accessorKey: "modules",
    header: "Modules",
    enableSorting: false,
    cell: ({ row }) => row.original.modules.join(", ") || "—",
  },
  { accessorKey: "timezone", header: "Timezone" },
];

export function OrganizationsTable({ organizations }: { organizations: Org[] }) {
  return (
    <DataTable
      caption="Organisations"
      columns={columns}
      data={organizations}
      getRowId={(o) => o.id}
      empty="No organisations yet."
    />
  );
}
