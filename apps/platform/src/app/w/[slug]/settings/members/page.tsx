import { workspaceWith } from "@/lib/settings-guard";
import { withApi } from "@/lib/api-client";
import { requireOk } from "@/lib/guards";

import { InviteForm } from "./invite-form";
import { MembersTable } from "./members-table";

type Props = { params: Promise<{ slug: string }> };

export default async function MembersSettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/settings/members`;
  const workspace = await workspaceWith(slug, "members.read", path);
  const members = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/members", { params: { path: { slug: workspace.slug } } }),
    ),
    path,
  );

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="members-heading" className="flex flex-col gap-4">
        <h2 id="members-heading" className="text-lg font-medium">
          Members
        </h2>
        <MembersTable members={members} />
      </section>
      {workspace.permissions.includes("invitations.create") ? (
        <section aria-labelledby="invite-heading" className="flex max-w-lg flex-col gap-4">
          <h2 id="invite-heading" className="text-lg font-medium">
            Invite someone
          </h2>
          <InviteForm slug={workspace.slug} canInviteOwner={workspace.role === "owner"} />
        </section>
      ) : null}
    </div>
  );
}
