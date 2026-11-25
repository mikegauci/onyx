"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { centsFrom, dealsPath } from "@/lib/deals";
import { type ApplicantType, bpFrom, type Estimate, type MaritalStatus } from "@/lib/finance";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

export type EstimateState = FormState & { estimate?: Estimate };

function money(formData: FormData, name: string, errors: Record<string, string>): number | null {
  const cents = centsFrom(text(formData, name));
  if (cents === "invalid") {
    errors[name] = "Enter an amount in euro, e.g. 16500 or 16,500.00.";
    return null;
  }
  return cents;
}

function months(formData: FormData, name: string, errors: Record<string, string>): number | null {
  const raw = text(formData, name);
  if (raw === "") return null;
  const years = Number(raw);
  if (!Number.isFinite(years) || years <= 0 || !Number.isInteger(years * 2)) {
    errors[name] = "Enter years in halves, e.g. 5 or 3.5.";
    return null;
  }
  return Math.round(years * 12);
}

export async function calculate(
  slug: string,
  _prev: EstimateState,
  formData: FormData,
): Promise<EstimateState> {
  const errors: Record<string, string> = {};
  const price = money(formData, "price", errors);
  const deposit = money(formData, "deposit", errors) ?? 0;
  const term = months(formData, "years", errors);
  const payoff = months(formData, "payoff_years", errors);
  if (price === null && !errors.price) errors.price = "Enter the vehicle price.";
  if (term === null && !errors.years) errors.years = "Enter the term in years.";
  if (Object.keys(errors).length || price === null || term === null) {
    return { status: "error", message: "Check the highlighted fields.", fieldErrors: errors };
  }
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/estimate", {
      params: { path: { slug } },
      body: {
        price_cents: price,
        deposit_cents: deposit,
        term_months: term,
        payoff_months: payoff,
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  return { status: "ok", estimate: outcome.data };
}

export async function createApplication(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const errors: Record<string, string> = {};
  const price = money(formData, "price", errors);
  const deposit = money(formData, "deposit", errors);
  const term = months(formData, "years", errors);
  const income = formData.has("income") ? money(formData, "income", errors) : null;
  const commitments = formData.has("commitments") ? money(formData, "commitments", errors) : null;
  if (Object.keys(errors).length) {
    return { status: "error", message: "Check the highlighted fields.", fieldErrors: errors };
  }
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/applications", {
      params: { path: { slug } },
      body: {
        contact_id: optionalText(formData, "contact_id"),
        deal_id: optionalText(formData, "deal_id"),
        applicant_type: text(formData, "applicant_type") as ApplicantType,
        marital_status: text(formData, "marital_status") as MaritalStatus,
        vehicle_label: optionalText(formData, "vehicle_label"),
        price_cents: price,
        deposit_cents: deposit,
        term_months: term,
        employer: formData.has("employer") ? optionalText(formData, "employer") : null,
        net_monthly_income_cents: income,
        existing_commitments_cents: commitments,
        notes: formData.has("notes") ? optionalText(formData, "notes") : null,
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  redirect(dealsPath(slug, "finance", outcome.data.id));
}

export async function changeApplicationStatus(
  slug: string,
  id: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/applications/{application_id}/status", {
      params: { path: { slug, application_id: id } },
      body: {
        status: text(formData, "status") as "started",
        note: optionalText(formData, "note"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug), "layout");
  return { status: "ok", message: "Status updated." };
}

export async function saveFinanceSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const fieldErrors: Record<string, string> = {};
  const rates: Record<string, number> = {};
  for (const name of ["annual_rate_bp", "onboarding_fee_bp", "yearly_fee_bp"]) {
    const bp = bpFrom(text(formData, name));
    if (bp === "invalid" || bp === null) fieldErrors[name] = "Enter a percentage, e.g. 6.5.";
    else rates[name] = bp;
  }
  const min = Number(text(formData, "min_years")) * 12;
  const max = Number(text(formData, "max_years")) * 12;
  if (!Number.isInteger(min) || min <= 0) fieldErrors.min_years = "Enter years, e.g. 0.5.";
  if (!Number.isInteger(max) || max < min) fieldErrors.max_years = "At least the shortest term.";
  if (Object.keys(fieldErrors).length) {
    return { status: "error", message: "Check the highlighted fields.", fieldErrors };
  }
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/finance/settings", {
      params: { path: { slug } },
      body: {
        ...rates,
        min_term_months: min,
        max_term_months: max,
        disclaimer: text(formData, "disclaimer"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug, "settings"));
  return { status: "ok", message: "Finance settings saved." };
}

export async function uploadFinanceForm(
  slug: string,
  kind: "kyc" | "ccr",
  file: { filename: string; content_base64: string },
): Promise<FormState> {
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/finance/forms/{kind}", {
      params: { path: { slug, kind } },
      body: file,
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  revalidatePath(dealsPath(slug, "settings"));
  return { status: "ok", message: "Form uploaded." };
}
