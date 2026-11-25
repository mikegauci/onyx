"use server";

import { revalidatePath } from "next/cache";

import { centsFromEuros, type ConsentMethod } from "@/lib/alerts";
import { mutateApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { crmPath } from "@/lib/crm";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

function refresh(slug: string) {
  revalidatePath(automotivePath(slug), "layout");
  revalidatePath(crmPath(slug), "layout");
}

type Criteria = {
  make: string | null;
  model: string | null;
  price_max_cents: number | null;
  year_min: number | null;
  mileage_max_km: number | null;
  fuel: string | null;
};

function criteria(formData: FormData): Criteria | FormState {
  const price = optionalText(formData, "price_max");
  const priceCents = price === null ? null : centsFromEuros(price);
  if (price !== null && priceCents === null) {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: { price_max_cents: "Enter an amount in euros, such as 18000." },
    };
  }
  const whole = (name: string) => {
    const value = optionalText(formData, name);
    return value === null ? null : Number.parseInt(value, 10);
  };
  return {
    make: optionalText(formData, "make"),
    model: optionalText(formData, "model"),
    price_max_cents: priceCents,
    year_min: whole("year_min"),
    mileage_max_km: whole("mileage_max_km"),
    fuel: optionalText(formData, "fuel"),
  };
}

function isState(value: Criteria | FormState): value is FormState {
  return "status" in value;
}

export async function saveWanted(
  slug: string,
  leadId: string,
  wantedId: string | null,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const body = criteria(formData);
  if (isState(body)) return body;
  const outcome = wantedId
    ? await mutateApi((api) =>
        api.PUT("/v1/w/{slug}/automotive/wanted/{wanted_id}", {
          params: { path: { slug, wanted_id: wantedId } },
          body: { ...body, active: formData.get("active") !== "off" },
        }),
      )
    : await mutateApi((api) =>
        api.POST("/v1/w/{slug}/automotive/leads/{lead_id}/wanted", {
          params: { path: { slug, lead_id: leadId } },
          body,
        }),
      );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  const found = outcome.data.pending_matches;
  return {
    status: "ok",
    message:
      found === 0
        ? "Saved. No car in stock matches yet; new arrivals are checked at each import."
        : `Saved. ${found} car${found === 1 ? "" : "s"} in stock match${found === 1 ? "es" : ""}.`,
  };
}

export async function confirmWanted(
  slug: string,
  wantedId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/wanted/{wanted_id}/confirm", {
      params: { path: { slug, wanted_id: wantedId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Confirmed. It now matches cars in stock." };
}

export type SendState = FormState & { sent?: number };

export async function sendMatches(
  slug: string,
  _prev: SendState,
  formData: FormData,
): Promise<SendState> {
  const ids = formData.getAll("match_id").map(String).filter(Boolean);
  if (ids.length === 0) return { status: "error", message: "Select at least one match." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/matches/send", {
      params: { path: { slug } },
      body: { match_ids: ids.slice(0, 50) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  const { sent, skipped } = outcome.data;
  const parts = [`${sent.length} alert${sent.length === 1 ? "" : "s"} sent.`];
  if (skipped.length > 0) {
    parts.push(
      `${skipped.length} not sent: ${[...new Set(skipped.map((s) => s.message))].join(" ")}`,
    );
  }
  return {
    status: skipped.length > 0 && sent.length === 0 ? "error" : "ok",
    message: parts.join(" "),
    sent: sent.length,
  };
}

export async function dismissMatch(
  slug: string,
  matchId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/matches/{match_id}/dismiss", {
      params: { path: { slug, match_id: matchId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Dismissed." };
}

export async function saveAlertSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const templateId = optionalText(formData, "template_id");
  const params = formData.getAll("param").map(String);
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/automotive/alert-settings", {
      params: { path: { slug } },
      body: { template_id: templateId, params: templateId ? params : [] },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: outcome.data.ready ? "Saved. Car alerts can be sent." : "Saved. Car alerts are off.",
  };
}

export async function grantConsent(
  slug: string,
  contactId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/crm/contacts/{contact_id}/consents/{purpose}", {
      params: { path: { slug, contact_id: contactId, purpose: "car_alerts" } },
      body: {
        method: text(formData, "method") as ConsentMethod,
        note: optionalText(formData, "note"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Consent recorded." };
}

export async function withdrawConsent(
  slug: string,
  contactId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/w/{slug}/crm/contacts/{contact_id}/consents/{purpose}", {
      params: { path: { slug, contact_id: contactId, purpose: "car_alerts" } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Consent withdrawn. No more car alerts go to this customer." };
}

export async function sendFollowups(
  slug: string,
  _prev: SendState,
  formData: FormData,
): Promise<SendState> {
  const ids = formData.getAll("followup_id").map(String).filter(Boolean);
  if (ids.length === 0) return { status: "error", message: "Select at least one follow-up." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/followups/send", {
      params: { path: { slug } },
      body: { followup_ids: ids.slice(0, 50) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  const { sent, skipped } = outcome.data;
  const parts = [`${sent.length} follow-up${sent.length === 1 ? "" : "s"} sent.`];
  if (skipped.length > 0) {
    parts.push(
      `${skipped.length} not sent: ${[...new Set(skipped.map((s) => s.message))].join(" ")}`,
    );
  }
  return {
    status: skipped.length > 0 && sent.length === 0 ? "error" : "ok",
    message: parts.join(" "),
    sent: sent.length,
  };
}

export async function dismissFollowup(
  slug: string,
  followupId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/followups/{followup_id}/dismiss", {
      params: { path: { slug, followup_id: followupId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Dismissed." };
}

export async function linkInterest(
  slug: string,
  leadId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const vehicleId = text(formData, "vehicle_id");
  if (!vehicleId) return { status: "error", message: "Choose a car." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/leads/{lead_id}/interests", {
      params: { path: { slug, lead_id: leadId } },
      body: { vehicle_id: vehicleId },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message: "Noted. If this car is sold, they will be offered similar cars.",
  };
}
