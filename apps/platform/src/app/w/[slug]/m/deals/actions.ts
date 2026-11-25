"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { centsFrom, type DealStage, dealsPath, type DepositMethod } from "@/lib/deals";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

function priceField(formData: FormData, name: string): number | null | FormState {
  const cents = centsFrom(text(formData, name));
  if (cents === "invalid") {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: { [name]: "Enter an amount in euro, e.g. 16500 or 16,500.00." },
    };
  }
  return cents;
}

export async function createDeal(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const price = priceField(formData, "price");
  if (price !== null && typeof price === "object") return price;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals", {
      params: { path: { slug } },
      body: {
        contact_id: optionalText(formData, "contact_id"),
        quote_id: optionalText(formData, "quote_id"),
        lead_id: optionalText(formData, "lead_id"),
        conversation_id: optionalText(formData, "conversation_id"),
        vehicle_id: optionalText(formData, "vehicle_id"),
        title: optionalText(formData, "title"),
        financed: formData.get("financed") === "on",
        has_trade_in: formData.get("has_trade_in") === "on",
        price_cents: price,
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug));
  redirect(dealsPath(slug, outcome.data.id));
}

export async function changeStage(
  slug: string,
  dealId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const stage = text(formData, "stage") as DealStage;
  if (!stage) return { status: "error", message: "Choose the new stage." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/{deal_id}/stage", {
      params: { path: { slug, deal_id: dealId } },
      body: {
        stage,
        reason: optionalText(formData, "reason"),
        override: formData.get("override") === "on",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: "Stage updated." };
}

export async function recordDeposit(
  slug: string,
  dealId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const amount = priceField(formData, "amount");
  if (amount !== null && typeof amount === "object") return amount;
  if (amount === null || amount <= 0) {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: { amount: "Enter the deposit amount." },
    };
  }
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/{deal_id}/deposit", {
      params: { path: { slug, deal_id: dealId } },
      body: {
        amount_cents: amount,
        received_on: text(formData, "received_on"),
        method: text(formData, "method") as DepositMethod,
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: "Deposit recorded." };
}

export async function updateDeal(
  slug: string,
  dealId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PATCH("/v1/w/{slug}/deals/{deal_id}", {
      params: { path: { slug, deal_id: dealId } },
      body: {
        financed: formData.get("financed") === "on",
        has_trade_in: formData.get("has_trade_in") === "on",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: "Deal updated. The checklist follows the changes." };
}

export async function addDocument(
  slug: string,
  dealId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/{deal_id}/documents", {
      params: { path: { slug, deal_id: dealId } },
      body: { label: text(formData, "label"), required: formData.get("required") === "on" },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug, dealId));
  return { status: "ok", message: "Added to the checklist." };
}

/** The file arrives already read in the browser (resized if it was a large photo). */
export async function uploadDocument(
  slug: string,
  dealId: string,
  documentId: string,
  file: { filename: string; content_base64: string },
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/{deal_id}/documents/{document_id}/file", {
      params: { path: { slug, deal_id: dealId, document_id: documentId } },
      body: file,
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: "Uploaded." };
}

export async function checkDocument(
  slug: string,
  dealId: string,
  documentId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const verdict = text(formData, "verdict");
  const path = { slug, deal_id: dealId, document_id: documentId };
  const outcome =
    verdict === "verify"
      ? await mutateApi((api) =>
          api.POST("/v1/w/{slug}/deals/{deal_id}/documents/{document_id}/verify", {
            params: { path },
          }),
        )
      : await mutateApi((api) =>
          api.POST("/v1/w/{slug}/deals/{deal_id}/documents/{document_id}/reject", {
            params: { path },
            body: { reason: text(formData, "reason") },
          }),
        );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: verdict === "verify" ? "Verified." : "Rejected." };
}

export async function saveSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const keys = formData.getAll("item_key").map(String);
  const labels = formData.getAll("item_label").map((v) => String(v).trim());
  const whens = formData.getAll("item_when").map(String);
  const notes = formData.getAll("item_note").map((v) => String(v).trim());
  const required = new Set(formData.getAll("item_required").map(String));
  const checklist = labels
    .map((label, i) => ({
      key:
        keys[i] ||
        `item_${label
          .toLowerCase()
          .replace(/[^a-z0-9]+/g, "_")
          .replace(/^_+|_+$/g, "")
          .slice(0, 30)}`,
      label,
      required: required.has(String(i)),
      note: notes[i] || null,
      when: (whens[i] || "always") as "always" | "financed" | "trade_in" | "deposit",
    }))
    .filter((item) => item.label !== "");
  const retention = Number(text(formData, "retention_days"));
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/settings", {
      params: { path: { slug } },
      body: {
        checklist,
        retention_days: Number.isInteger(retention) ? retention : 0,
        customer_reminders: formData.get("customer_reminders") === "on",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug, "settings"));
  return { status: "ok", message: "Deal settings saved. New deals use this checklist." };
}
