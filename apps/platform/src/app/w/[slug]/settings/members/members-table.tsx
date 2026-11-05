"use client";

import type { components } from "@onyx/api-client";
import { Badge } from "@onyx/ui/components/badge";
import { type ColumnDef, DataTable } from "@onyx/ui/components/data-table";

type Member = components["schemas"]["MemberOut"];

const columns: ColumnDef<Member>[] = [
  { accessorKey: "display_name", header: "Name" },
  { accessorKey: "email", header: "Email" },
  {
    accessorKey: "role",
    header: "Role",
    cell: ({ row }) => <Badge variant="secondary">{row.original.role}</Badge>,
  },
];

export function MembersTable({ members }: { members: Member[] }) {
  return (
    <DataTable
      caption="Workspace members"
      columns={columns}
      data={members}
      getRowId={(m) => m.user_id}
      empty="No members yet."
    />
  );
}
