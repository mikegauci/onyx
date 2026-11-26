"use server";

import { revalidatePath } from "next/cache";

import { mutateApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { crmPath } from "@/lib/crm";
import { type FormState, failureState, optionalText, text } from "@/lib/form-state";
import { REMINDER_KINDS } from "@/lib/reminders";

export type SendState = FormState & { sent?: number };

function refresh(slug: string) {
  revalidatePath(automotivePath(slug), "layout");
  revalidatePath(crmPath(slug), "layout");
}

function carBody(formData: FormData) {
  const interval = Number.parseInt(text(formData, "service_interval_months") || "12", 10);
  return {
    description: text(formData, "description"),
    registration: optionalText(formData, "registration"),
    collected_on: optionalText(formData, "collected_on"),
    licence_due_on: optionalText(formData, "licence_due_on"),
    dealer_handles_licence: formData.get("dealer_handles_licence") === "on",
    insurance_due_on: optionalText(formData, "insurance_due_on"),
    dealer_handles_insurance: formData.get("dealer_handles_insurance") === "on",
    last_service_on: optionalText(formData, "last_service_on"),
    service_interval_months: Number.isFinite(interval) ? interval : 12,
    reminders_paused: formData.get("reminders_paused") === "on",
  };
}

export async function saveCustomerCar(
  slug: string,
  contactId: string,
  carId: string | null,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const body = carBody(formData);
  if (!body.description) {
    return {
      status: "error",
      message: "Check the highlighted fields.",
      fieldErrors: { description: "Describe the car, for example “Volkswagen Golf 2019”." },
    };
  }
  const outcome = carId
    ? await mutateApi((api) =>
        api.PUT("/v1/w/{slug}/automotive/customer-cars/{car_id}", {
          params: { path: { slug, car_id: carId } },
          body,
        }),
      )
    : await mutateApi((api) =>
        api.POST("/v1/w/{slug}/automotive/customer-cars", {
          params: { path: { slug } },
          body: { ...body, contact_id: contactId },
        }),
      );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: carId ? "Car updated." : "Car added." };
}

export async function recordService(
  slug: string,
  carId: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const servicedOn = text(formData, "serviced_on");
  if (!servicedOn) return { status: "error", message: "Choose the service date." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/customer-cars/{car_id}/service", {
      params: { path: { slug, car_id: carId } },
      body: { serviced_on: servicedOn },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Service recorded. The next one is due an interval later." };
}

export async function sendReminders(
  slug: string,
  _prev: SendState,
  formData: FormData,
): Promise<SendState> {
  const ids = formData.getAll("reminder_id").map(String).filter(Boolean);
  if (ids.length === 0) return { status: "error", message: "Select at least one reminder." };
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/reminders/send", {
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

export async function dismissReminder(
  slug: string,
  reminderId: string,
  _prev: FormState,
): Promise<FormState> {
  void _prev;
  const outcome = await mutateApi((api) =>
    api.POST("/v1/w/{slug}/automotive/reminders/{reminder_id}/dismiss", {
      params: { path: { slug, reminder_id: reminderId } },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Dismissed." };
}

export async function saveReminderSettings(
  slug: string,
  _prev: FormState,
  formData: FormData,
): Promise<FormState> {
  const kind = (k: (typeof REMINDER_KINDS)[number]) => {
    const days = Number.parseInt(text(formData, `${k}_days`) || "30", 10);
    const templateId = optionalText(formData, `${k}_template_id`);
    return {
      days: Number.isFinite(days) ? days : 30,
      message: optionalText(formData, `${k}_message`),
      template_id: templateId,
      params: templateId ? formData.getAll(`${k}_param`).map(String) : [],
    };
  };
  const outcome = await mutateApi((api) =>
    api.PUT("/v1/w/{slug}/automotive/reminder-settings", {
      params: { path: { slug } },
      body: { licence: kind("licence"), insurance: kind("insurance"), service: kind("service") },
    }),
  );
  if (!outcome.ok) return failureState(outcome);
  refresh(slug);
  return { status: "ok", message: "Saved." };
}
