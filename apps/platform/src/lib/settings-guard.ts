import "server-only";

import { notFound } from "next/navigation";

import type { Permission, Workspace } from "./api-client";
import { getWorkspace } from "./data";
import { requireOk } from "./guards";

/** The workspace, if the caller holds `permission` there; the not-found page otherwise. */
export async function workspaceWith(
  slug: string,
  permission: Permission,
  path: string,
): Promise<Workspace> {
  const workspace = requireOk(await getWorkspace(slug), path);
  if (!workspace.permissions.includes(permission)) notFound();
  return workspace;
}
