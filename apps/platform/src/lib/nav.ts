import type { Permission } from "./api-client";

export type SettingsSection = {
  slug: string;
  label: string;
  /** Shown only when the caller holds this permission; the API enforces it regardless. */
  permission?: Permission;
};

export const SETTINGS_SECTIONS: SettingsSection[] = [
  { slug: "general", label: "General", permission: "workspace.update" },
  { slug: "members", label: "Members", permission: "members.read" },
  { slug: "audit", label: "Audit log", permission: "audit.read" },
  { slug: "modules", label: "Modules", permission: "workspace.update" },
  { slug: "integrations", label: "Integrations", permission: "workspace.update" },
  { slug: "billing", label: "Billing", permission: "workspace.update" },
];

export function visibleSettings(permissions: readonly Permission[]): SettingsSection[] {
  return SETTINGS_SECTIONS.filter((s) => !s.permission || permissions.includes(s.permission));
}

export function isActive(pathname: string, href: string, exact = false): boolean {
  return exact ? pathname === href : pathname === href || pathname.startsWith(`${href}/`);
}
