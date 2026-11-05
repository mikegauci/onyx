"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { type QuoteWarning, quotationsPath } from "@/lib/quotations";

function done(slug: string, message: string): FormState {
  revalidatePath(quotationsPath(slug), "layout");
  return { status: "ok", message };
}

const ids = (slug: string, quoteId: string) => ({ path: { slug, quote_id: quoteId } });

export async function createQuote(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/quotations/quotes", {
      params: { path: { slug } },
      body: {
        title: text(formData, "title"),
        contact_id: text(formData, "contact_id"),
        lead_id: optionalText(formData, "lead_id"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(quotationsPath(slug), "layout");
  redirect(quotationsPath(slug, "quotes", outcome.data.id));
}

export async function addSkuLine(
  slug: string,
  quoteId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/lines", {
      params: ids(slug, quoteId),
      body: {
        kind: "catalogue",
        sku: text(formData, "sku"),
        quantity: Number(text(formData, "quantity") || "1"),
        discount_percent: text(formData, "discount_percent") || "0",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Line added.");
}

export async function addCustomLine(
  slug: string,
  quoteId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/lines", {
      params: ids(slug, quoteId),
      body: {
        kind: "custom",
        description: text(formData, "description"),
        unit_price: text(formData, "unit_price"),
        vat_rate_id: text(formData, "vat_rate_id"),
        quantity: Number(text(formData, "quantity") || "1"),
        discount_percent: text(formData, "discount_percent") || "0",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Line added.");
}

export async function updateLine(
  slug: string,
  quoteId: string,
  lineId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/quotations/quotes/{quote_id}/lines/{line_id}", {
      params: { path: { slug, quote_id: quoteId, line_id: lineId } },
      body: {
        quantity: Number(text(formData, "quantity")),
        discount_percent: text(formData, "discount_percent") || "0",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Line updated.");
}

export async function refreshLine(
  slug: string,
  quoteId: string,
  lineId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/lines/{line_id}/refresh", {
      params: { path: { slug, quote_id: quoteId, line_id: lineId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Price and VAT updated from the catalogue.");
}

export async function removeLine(
  slug: string,
  quoteId: string,
  lineId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.DELETE("/v1/w/{slug}/quotations/quotes/{quote_id}/lines/{line_id}", {
      params: { path: { slug, quote_id: quoteId, line_id: lineId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Line removed.");
}

export async function updateQuote(
  slug: string,
  quoteId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/quotations/quotes/{quote_id}", {
      params: ids(slug, quoteId),
      body: { title: text(formData, "title"), notes: optionalText(formData, "notes") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Quote saved.");
}

export async function approveQuote(
  slug: string,
  quoteId: string,
  version: number,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  // Each confirmed warning arrives as "line_id:code".
  const acknowledge = formData
    .getAll("acknowledge")
    .map(String)
    .map((value) => {
      const [lineId, code] = value.split(":");
      return { line_id: lineId ?? "", code: code as QuoteWarning["code"] };
    });
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/approve", {
      params: ids(slug, quoteId),
      body: { version, acknowledge },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, `Version ${version} approved.`);
}

export async function quoteAction(
  slug: string,
  quoteId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const action = text(formData, "action");
  const reason = optionalText(formData, "reason");
  const params = ids(slug, quoteId);
  const outcome =
    action === "revise"
      ? await mutateApi((api) =>
          api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/revise", { params }),
        )
      : action === "cancel"
        ? await mutateApi((api) =>
            api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/cancel", {
              params,
              body: { reason },
            }),
          )
        : await mutateApi((api) =>
            api.POST("/v1/w/{slug}/quotations/quotes/{quote_id}/outcome", {
              params,
              body: { outcome: action === "accept" ? "accepted" : "declined", reason },
            }),
          );
  if (!outcome.ok) return failureState(outcome);
  const label: Record<string, string> = {
    revise: `Version ${outcome.data.version} started as a draft.`,
    cancel: "Quote cancelled.",
    accept: "Recorded as accepted.",
    decline: "Recorded as declined.",
  };
  return done(slug, label[action] ?? "Saved.");
}

export async function saveSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/quotations/settings", {
      params: { path: { slug } },
      body: {
        number_prefix: text(formData, "number_prefix"),
        validity_days: Number(text(formData, "validity_days")),
        max_discount_percent: text(formData, "max_discount_percent"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return done(slug, "Settings saved.");
}
