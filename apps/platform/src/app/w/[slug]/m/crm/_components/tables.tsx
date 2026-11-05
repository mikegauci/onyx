"use client";

import { Badge } from "@onyx/ui/components/badge";
import { type ColumnDef, DataTable } from "@onyx/ui/components/data-table";
import Link from "next/link";

import {
  type Contact,
  type Customer,
  type Lead,
  STATUS_LABEL,
  STATUS_VARIANT,
  crmPath,
  formatInZone,
} from "@/lib/crm";

const LINK = "font-medium underline-offset-4 hover:underline";

export function LeadsTable({
  slug,
  leads,
  timezone,
  caption = "Leads",
}: {
  slug: string;
  leads: Lead[];
  timezone: string;
  caption?: string;
}) {
  const columns: ColumnDef<Lead>[] = [
    {
      accessorKey: "title",
      header: "Lead",
      cell: ({ row }) => (
        <span className="flex items-center gap-2">
          <Link className={LINK} href={crmPath(slug, "leads", row.original.id)}>
            {row.original.title}
          </Link>
          {row.original.archived_at ? <Badge variant="outline">Archived</Badge> : null}
        </span>
      ),
    },
    {
      id: "contact",
      accessorFn: (lead) => lead.contact.full_name,
      header: "Contact",
      cell: ({ row }) => (
        <Link className={LINK} href={crmPath(slug, "contacts", row.original.contact.id)}>
          {row.original.contact.full_name}
        </Link>
      ),
    },
    {
      id: "customer",
      accessorFn: (lead) => lead.customer?.name ?? "",
      header: "Customer",
    },
    {
      accessorKey: "status",
      header: "Status",
      cell: ({ row }) => (
        <Badge variant={STATUS_VARIANT[row.original.status]}>
          {STATUS_LABEL[row.original.status]}
        </Badge>
      ),
    },
    {
      id: "owner",
      accessorFn: (lead) => lead.owner?.display_name ?? "",
      header: "Owner",
    },
    {
      accessorKey: "created_at",
      header: "Created",
      cell: ({ row }) => formatInZone(row.original.created_at, timezone),
    },
  ];
  return (
    <DataTable
      caption={caption}
      columns={columns}
      data={leads}
      getRowId={(lead) => lead.id}
      empty="No leads yet."
    />
  );
}

export function ContactsTable({ slug, contacts }: { slug: string; contacts: Contact[] }) {
  const columns: ColumnDef<Contact>[] = [
    {
      accessorKey: "full_name",
      header: "Name",
      cell: ({ row }) => (
        <span className="flex items-center gap-2">
          <Link className={LINK} href={crmPath(slug, "contacts", row.original.id)}>
            {row.original.full_name}
          </Link>
          {row.original.archived_at ? <Badge variant="outline">Archived</Badge> : null}
        </span>
      ),
    },
    { id: "email", accessorFn: (c) => c.email ?? "", header: "Email" },
    { id: "phone", accessorFn: (c) => c.phone ?? "", header: "Phone" },
    { id: "customer", accessorFn: (c) => c.customer?.name ?? "", header: "Customer" },
  ];
  return (
    <DataTable
      caption="Contacts"
      columns={columns}
      data={contacts}
      getRowId={(contact) => contact.id}
      empty="No contacts yet."
    />
  );
}

export function CustomersTable({ slug, customers }: { slug: string; customers: Customer[] }) {
  const columns: ColumnDef<Customer>[] = [
    {
      accessorKey: "name",
      header: "Name",
      cell: ({ row }) => (
        <span className="flex items-center gap-2">
          <Link className={LINK} href={crmPath(slug, "customers", row.original.id)}>
            {row.original.name}
          </Link>
          {row.original.archived_at ? <Badge variant="outline">Archived</Badge> : null}
        </span>
      ),
    },
    {
      accessorKey: "kind",
      header: "Type",
      cell: ({ row }) => (row.original.kind === "business" ? "Business" : "Individual"),
    },
    { id: "vat", accessorFn: (c) => c.vat_number ?? "", header: "VAT number" },
  ];
  return (
    <DataTable
      caption="Customers"
      columns={columns}
      data={customers}
      getRowId={(customer) => customer.id}
      empty="No customers yet."
    />
  );
}
