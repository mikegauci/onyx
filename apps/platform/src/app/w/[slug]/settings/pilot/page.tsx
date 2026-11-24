import { formatInZone } from "@/lib/crm";
import { getControls } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ManualModeForm, SwitchesForm } from "./pilot-forms";

type Props = { params: Promise<{ slug: string }> };

export default async function PilotControlsPage({ params }: Props) {
  const { slug } = await params;
  const path = `/w/${slug}/settings/pilot`;
  const workspace = await workspaceWith(slug, "workspace.update", path);
  const controls = requireOk(await getControls(slug), path);

  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="manual-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <div className="flex flex-col gap-1">
          <h2 id="manual-heading" className="text-base font-medium tracking-tight">
            Manual mode
          </h2>
          <p className="text-muted-foreground text-sm">
            Humans only. Onyx stops drafting with the assistant and stops sending anything
            automatically, such as missed-call text-backs. Messages still arrive in the inbox and
            staff reply, approve and send as normal. Turning it off restores the switches below.
          </p>
        </div>
        <ManualModeForm
          slug={workspace.slug}
          on={controls.manual_mode}
          reason={controls.manual_mode_reason}
        />
      </section>

      <section
        aria-labelledby="switches-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <div className="flex flex-col gap-1">
          <h2 id="switches-heading" className="text-base font-medium tracking-tight">
            Feature switches
          </h2>
          <p className="text-muted-foreground text-sm">
            Pause one feature for this workspace without changing the plan. Changes apply on the
            next request and are recorded in the audit log.
          </p>
        </div>
        <SwitchesForm
          slug={workspace.slug}
          controls={controls}
          hasAssistant={workspace.modules.includes("assistant")}
          hasInbox={workspace.modules.includes("inbox")}
        />
        {controls.updated_at ? (
          <p className="text-muted-foreground text-xs">
            Last changed{" "}
            <time dateTime={controls.updated_at}>
              {formatInZone(controls.updated_at, workspace.timezone)}
            </time>
            . See Settings → Audit log for who changed what.
          </p>
        ) : null}
      </section>
    </div>
  );
}
