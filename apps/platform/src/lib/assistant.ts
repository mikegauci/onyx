/** Display helpers for the sales assistant. Every rule and reason text comes from the API. */
import type { components } from "@onyx/api-client";

export type AssistantRun = components["schemas"]["RunOut"];
export type AssistantPolicy = components["schemas"]["PolicyOut"];
export type RunOutcome = components["schemas"]["RunOutcome"];

/** A run makes several model requests in one API call; allow for retries before giving up. */
export const RUN_TIMEOUT_MS = 120_000;

export function assistantPath(slug: string, ...parts: string[]): string {
  return [`/w/${encodeURIComponent(slug)}/m/assistant`, ...parts].join("/");
}

export const OUTCOME_LABEL: Record<RunOutcome, string> = {
  drafted: "Draft quote created",
  escalated: "Handed to staff",
};

export const OUTCOME_VARIANT: Record<RunOutcome, "success" | "warning"> = {
  drafted: "success",
  escalated: "warning",
};

/** Integer micro-USD to a short dollar string, without floating-point arithmetic. */
export function usdFromMicros(micros: number): string {
  const whole = Math.trunc(micros);
  const sign = whole < 0 ? "-" : "";
  const digits = String(Math.abs(whole)).padStart(7, "0");
  const dollars = digits.slice(0, -6);
  // Four decimal places is enough to tell runs apart; truncate the rest.
  const cents = digits.slice(-6, -2);
  return `${sign}$${dollars}.${cents}`;
}

/** Policy topics are lower-case slugs; the API validates them too. */
export const TOPIC_PATTERN = /^[a-z][a-z0-9_]{1,39}$/;

export function topicLabel(topic: string): string {
  const words = topic.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Why the button cannot be used right now, or null when it can. */
export function runBlockedReason(status: components["schemas"]["ConversationStatus"]) {
  return status === "closed" ? "Reopen the conversation to ask the assistant." : null;
}
