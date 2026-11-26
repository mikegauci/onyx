"use server";

import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

import { mutateApi } from "@/lib/api-client";
import { centsFrom, dealsPath } from "@/lib/deals";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";

function refresh(slug: string) {
  revalidatePath(dealsPath(slug), "layout");
}

function amount(formData: FormData, name: string): number | null | "invalid" {
  return centsFrom(text(formData, name));
}

function invalid(field: string, message: string): FormState {
  return {
    status: "error",
    message: "Check the highlighted fields.",
    fieldErrors: { [field]: message },
  };
}

export async function createSchedule(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const total = amount(formData, "total");
  if (total === "invalid") return invalid("total_cents", "Enter an amount in euros.");
  const monthly = amount(formData, "monthly");
  if (monthly === "invalid") return invalid("monthly_cents", "Enter an amount in euros.");
  const term = optionalText(formData, "term_months");
  const firstDue = text(formData, "first_due_on");
  if (!firstDue) return invalid("first_due_on", "Choose the first due date.");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/schedules", {
      params: { path: { slug } },
      body: {
        deal_id: optionalText(formData, "deal_id"),
        contact_id: optionalText(formData, "contact_id"),
        label: optionalText(formData, "label"),
        total_cents: total,
        term_months: term ? Number.parseInt(term, 10) : null,
        monthly_cents: monthly,
        first_due_on: firstDue,
        note: optionalText(formData, "note"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  redirect(dealsPath(slug, "finance", "schedules", outcome.data.id));
}

export async function recordPayment(
  slug: string,
  scheduleId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const cents = amount(formData, "amount");
  if (cents === null || cents === "invalid" || cents <= 0) {
    return invalid("amount_cents", "Enter the amount received in euros.");
  }
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/schedules/{schedule_id}/payments", {
      params: { path: { slug, schedule_id: scheduleId } },
      body: {
        amount_cents: cents,
        received_on: text(formData, "received_on"),
        method: (text(formData, "method") || "bank_transfer") as
          "cash" | "bank_transfer" | "card" | "cheque" | "other",
        note: optionalText(formData, "note"),
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return {
    status: "ok",
    message:
      outcome.data.status === "completed" ? "Payment recorded. Paid in full." : "Payment recorded.",
  };
}

export async function voidPayment(
  slug: string,
  scheduleId: string,
  paymentId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const reason = text(formData, "reason");
  if (!reason) return invalid("reason", "Say why this payment is being voided.");
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/schedules/{schedule_id}/payments/{payment_id}/void", {
      params: { path: { slug, schedule_id: scheduleId, payment_id: paymentId } },
      body: { reason },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Payment voided." };
}

export async function updateSchedule(
  slug: string,
  scheduleId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const label = text(formData, "label");
  if (!label) return invalid("label", "Describe the car.");
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/finance/schedules/{schedule_id}", {
      params: { path: { slug, schedule_id: scheduleId } },
      body: {
        label,
        note: optionalText(formData, "note"),
        reminders_paused: formData.get("reminders_paused") === "on",
        cancelled: formData.get("cancelled") === "on",
      },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Saved." };
}

export async function updateInstallment(
  slug: string,
  scheduleId: string,
  installmentId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const cents = amount(formData, "amount");
  if (cents === null || cents === "invalid" || cents <= 0) {
    return invalid("amount_cents", "Enter an amount in euros.");
  }
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/finance/schedules/{schedule_id}/installments/{installment_id}", {
      params: { path: { slug, schedule_id: scheduleId, installment_id: installmentId } },
      body: { due_on: text(formData, "due_on"), amount_cents: cents },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Installment changed." };
}

export type SendState = FormState & { sent?: number };

export async function sendPaymentReminders(
  slug: string,
  _prev: SendState,
  formData: FormData,
): Promise<SendState> {
  const ids = formData.getAll("reminder_id").map(String).filter(Boolean);
  if (ids.length === 0) return { status: "error", message: "Select at least one reminder." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/reminders/send", {
      params: { path: { slug } },
      body: { reminder_ids: ids.slice(0, 50) },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  const { sent, skipped } = outcome.data;
  const parts = [`${sent.length} reminder${sent.length === 1 ? "" : "s"} sent.`];
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

export async function dismissPaymentReminder(
  slug: string,
  reminderId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/deals/finance/reminders/{reminder_id}/dismiss", {
      params: { path: { slug, reminder_id: reminderId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Dismissed." };
}

export async function savePaymentReminderSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const kind = (k: "before_due" | "overdue") => {
    const days = Number.parseInt(text(formData, `${k}_days`) || "3", 10);
    const templateId = optionalText(formData, `${k}_template_id`);
    return {
      days: Number.isFinite(days) ? days : 3,
      message: optionalText(formData, `${k}_message`),
      template_id: templateId,
      params: templateId ? formData.getAll(`${k}_param`).map(String) : [],
    };
  };
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/deals/finance/reminder-settings", {
      params: { path: { slug } },
      body: { before_due: kind("before_due"), overdue: kind("overdue") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Saved." };
}
