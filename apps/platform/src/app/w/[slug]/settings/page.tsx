import { notFound, redirect } from "next/navigation";

import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { visibleSettings } from "@/lib/nav";

type Props = { params: Promise<{ slug: string }> };

export default async function SettingsIndex({ params }: Props) {
  const { slug } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}/settings`);
  const first = visibleSettings(workspace.permissions)[0];
  if (!first) notFound();
  redirect(`/w/${workspace.slug}/settings/${first.slug}`);
}
