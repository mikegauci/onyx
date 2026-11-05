import { notFound } from "next/navigation";
import type { ReactNode } from "react";

import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { visibleSettings } from "@/lib/nav";

import { SettingsNav } from "./settings-nav";

type Props = { children: ReactNode; params: Promise<{ slug: string }> };

export default async function SettingsLayout({ children, params }: Props) {
  const { slug } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}/settings`);
  const sections = visibleSettings(workspace.permissions);
  // Hidden from members; the API rejects their requests regardless.
  if (sections.length === 0) notFound();

  return (
    <div className="flex flex-col gap-6">
      <h1 className="text-2xl font-semibold tracking-tight">Settings</h1>
      <div className="flex flex-col gap-6 md:flex-row">
        <SettingsNav
          base={`/w/${workspace.slug}/settings`}
          sections={sections.map(({ slug: s, label }) => ({ slug: s, label }))}
        />
        <div className="min-w-0 flex-1">{children}</div>
      </div>
    </div>
  );
}
