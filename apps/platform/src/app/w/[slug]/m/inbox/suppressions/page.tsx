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

import { withApi } from "@/lib/api-client";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { inboxPath, type Suppression, SUPPRESSION_REASON_LABEL } from "@/lib/inbox";
import { workspaceWith } from "@/lib/settings-guard";

import { AddSuppressionForm, ReleaseSuppression } from "../_components/suppression-forms";

/** Addresses Onyx will not email. The API enforces this on every send. */
export default async function SuppressionsPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = inboxPath(slug, "suppressions");
  const workspace = await workspaceWith(slug, "inbox.read", path);
  const suppressions = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/inbox/suppressions", { params: { path: { slug } } }),
    ),
    path,
  ).items;
  const canWrite = workspace.permissions.includes("inbox.write");
  const canManage = workspace.permissions.includes("inbox.manage");

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-4" aria-labelledby="suppressions-heading">
        <h2 id="suppressions-heading" className="text-lg font-medium">
          Blocked addresses
        </h2>
        <p className="text-muted-foreground text-sm">
          Onyx does not email these addresses. Bounced and spam-marked addresses are added
          automatically, so replies stop before they harm the sending domain.
        </p>
        {suppressions.length === 0 ? (
          <p className="text-sm">No blocked addresses.</p>
        ) : (
          <Table>
            <TableCaption className="sr-only">Blocked addresses</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Address</TableHead>
                <TableHead>Reason</TableHead>
                <TableHead>Added</TableHead>
                {canManage ? (
                  <TableHead>
                    <span className="sr-only">Actions</span>
                  </TableHead>
                ) : null}
              </TableRow>
            </TableHeader>
            <TableBody>
              {suppressions.map((s) => (
                <TableRow key={s.id}>
                  <TableCell className="font-medium break-all">{s.address}</TableCell>
                  <TableCell>
                    <Badge variant={s.reason === "manual" ? "outline" : "destructive"}>
                      {SUPPRESSION_REASON_LABEL[s.reason]}
                    </Badge>
                    {s.note ? <p className="text-muted-foreground mt-1 text-xs">{s.note}</p> : null}
                  </TableCell>
                  <TableCell className="text-sm">
                    {addedBy(s)}
                    {" · "}
                    <time dateTime={s.created_at}>
                      {formatInZone(s.created_at, workspace.timezone)}
                    </time>
                  </TableCell>
                  {canManage ? (
                    <TableCell>
                      <ReleaseSuppression slug={slug} suppression={s} />
                    </TableCell>
                  ) : null}
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
      {canWrite ? (
        <section className="flex flex-col gap-4" aria-labelledby="new-suppression-heading">
          <h2 id="new-suppression-heading" className="text-lg font-medium">
            Block an address
          </h2>
          <AddSuppressionForm slug={slug} />
        </section>
      ) : null}
    </div>
  );
}

function addedBy(s: Suppression): string {
  if (s.created_by) return s.created_by.display_name ?? "A member";
  return s.reason === "manual" ? "Former member" : "Automatically";
}
