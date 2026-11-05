"use client";

import type { components } from "@onyx/api-client";
import { Badge } from "@onyx/ui/components/badge";
import { type ColumnDef, DataTable } from "@onyx/ui/components/data-table";

type Module = components["schemas"]["ModuleOut"];

export function EnabledBadge({ enabled }: { enabled: boolean }) {
  return enabled ? <Badge>Enabled</Badge> : <Badge variant="outline">Not enabled</Badge>;
}

const columns: ColumnDef<Module>[] = [
  { accessorKey: "name", header: "Module" },
  { accessorKey: "description", header: "Description", enableSorting: false },
  {
    accessorKey: "enabled",
    header: "Status",
    cell: ({ row }) => <EnabledBadge enabled={row.original.enabled} />,
  },
  {
    accessorKey: "requires",
    header: "Requires",
    enableSorting: false,
    cell: ({ row }) => row.original.requires.join(", ") || "—",
  },
];

export function ModulesTable({ modules }: { modules: Module[] }) {
  return <DataTable caption="Modules" columns={columns} data={modules} getRowId={(m) => m.key} />;
}
