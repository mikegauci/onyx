"use server";

import type { components } from "@onyx/api-client";
import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { platformEnv } from "@/lib/env";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { inviteLink } from "@/lib/tenants";

/** A form state that may carry a one-time invitation link (shown once, never stored). */
export type AdminFormState = FormState & { inviteLink?: string; slug?: string };

function refresh(slug?: string) {
  revalidatePath("/admin");
  if (slug) revalidatePath(`/admin/organizations/${slug}`);
}

function micros(formData: FormData, name: string): number | null {
  const raw = text(formData, name);
  if (raw === "") return null;
  const dollars = Number(raw);
  return Number.isFinite(dollars) ? Math.round(dollars * 1_000_000) : -1;
}

/** Create the organisation, its modules and budget, and its first owner's invitation. */
export async function createOrganization(
  _prev: AdminFormState,
  formData: FormData,
): Promise<AdminFormState> {
  const slug = text(formData, "slug");
  const budget = micros(formData, "ai_budget");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/admin/organizations", {
      body: {
        slug,
        name: text(formData, "name"),
        timezone: text(formData, "timezone") || "Europe/Malta",
        currency: "EUR",
        display_name: optionalText(formData, "display_name"),
        brand_color: optionalText(formData, "brand_color"),
        owner_email: text(formData, "owner_email"),
        modules: formData
          .getAll("modules")
          .filter((m): m is components["schemas"]["ModuleKey"] => typeof m === "string"),
        ai_alert_percent: 80,
        ...(budget === null ? {} : { ai_monthly_limit_usd_micros: budget }),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh();
  return {
    status: "ok",
    message: `${outcome.data.organization.organization.name} created. Send this one-time link to ${outcome.data.invitation.email}; it is not shown again and expires in 7 days.`,
    inviteLink: inviteLink(platformEnv().appUrl, outcome.data.invitation.token),
    slug: outcome.data.organization.organization.slug,
  };
}

/** Name, timezone, display name and brand colour. An empty optional field clears it. */
export async function updateOrganization(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/admin/organizations/{slug}", {
      params: { path: { slug } },
      body: {
        name: text(formData, "name"),
        timezone: text(formData, "timezone"),
        display_name: optionalText(formData, "display_name"),
        brand_color: optionalText(formData, "brand_color"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Details saved." };
}

export async function setOrganizationStatus(
  slug: string,
  status: "active" | "suspended",
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/admin/organizations/{slug}/status", {
      params: { path: { slug } },
      body: { status },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message:
      status === "suspended"
        ? "Suspended. Its members are locked out and its email and WhatsApp are dropped."
        : "Reactivated. Its members have access again.",
  };
}

/** A new invitation link; an open one to the same address is revoked. */
export async function issueInvitation(
  slug: string,
  _prev: AdminFormState,
  formData: FormData,
): Promise<AdminFormState> {
  const role = text(formData, "role");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/admin/organizations/{slug}/invitations", {
      params: { path: { slug } },
      body: {
        email: text(formData, "email"),
        role: role === "admin" || role === "member" ? role : "owner",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: `New link for ${outcome.data.email}. It is not shown again; any earlier open link to this address no longer works.`,
    inviteLink: inviteLink(platformEnv().appUrl, outcome.data.token),
  };
}

export async function revokeInvitation(
  slug: string,
  invitationId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/admin/organizations/{slug}/invitations/{invitation_id}/revoke", {
      params: { path: { slug, invitation_id: invitationId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Invitation revoked. Its link no longer works." };
}

export async function setAIBudget(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const limit = micros(formData, "ai_budget");
  const alert = Number(text(formData, "alert_percent") || "80");
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/admin/organizations/{slug}/ai-budget", {
      params: { path: { slug } },
      body: { monthly_limit_usd_micros: limit ?? -1, alert_percent: alert },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "AI budget saved." };
}

/** Attach a WhatsApp business number (Meta) to the organisation's WhatsApp channel. */
export async function connectWhatsApp(
  slug: string,
  _prev: AdminFormState,
  formData: FormData,
): Promise<AdminFormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/admin/organizations/{slug}/whatsapp-channels", {
      params: { path: { slug } },
      body: {
        channel_name: text(formData, "channel_name") || "WhatsApp",
        phone_number_id: text(formData, "phone_number_id"),
        waba_id: text(formData, "waba_id"),
        display_phone_number: text(formData, "display_phone_number"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message:
      "WhatsApp number connected. Ask the owner to press “Refresh from WhatsApp” under Inbox → Channels to load the templates.",
  };
}

/** Connect a cloud number for missed-call text-back, threaded into a WhatsApp channel. */
export async function connectPhoneLine(
  slug: string,
  _prev: AdminFormState,
  formData: FormData,
): Promise<AdminFormState> {
  const number = text(formData, "number").replace(/[\s()-]/g, "");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/admin/organizations/{slug}/phone-lines", {
      params: { path: { slug } },
      body: { number, whatsapp_channel_name: text(formData, "whatsapp_channel_name") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: `Phone line ${number} connected. The owner sets the text-back message under Inbox → Channels.`,
  };
}

/** Remove the business number from a WhatsApp channel (to replace it, connect a new one). */
export async function disconnectWhatsApp(
  slug: string,
  channelId: string,
  _prev: AdminFormState,
): Promise<AdminFormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/admin/organizations/{slug}/whatsapp-channels/{channel_id}/number", {
      params: { path: { slug, channel_id: channelId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: "Number disconnected. Connect the new number to the same channel name to replace it.",
  };
}

export async function disconnectPhoneLine(
  slug: string,
  lineId: string,
  _prev: AdminFormState,
): Promise<AdminFormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/admin/organizations/{slug}/phone-lines/{line_id}", {
      params: { path: { slug, line_id: lineId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Phone line disconnected. Its missed-call history stays." };
}
