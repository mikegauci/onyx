/** Display helpers for finance (VA-006). Figures and rules come from the API. */
import type { components } from "@onyx/api-client";

export type FinanceApplication = components["schemas"]["FinanceApplicationDetail"];
export type FinanceSummary = components["schemas"]["FinanceApplicationSummary"];
export type Estimate = components["schemas"]["EstimateOut"];
export type FinanceSettings = components["schemas"]["FinanceSettingsOut"];
export type ApplicantType = components["schemas"]["ApplicantType"];
export type MaritalStatus = components["schemas"]["MaritalStatus"];
export type ApplicationStatus = components["schemas"]["ApplicationStatus"];

export const APPLICANT_LABEL: Record<ApplicantType, string> = {
  maltese_resident: "Maltese resident",
  non_maltese_resident: "Non-Maltese resident",
  self_employed: "Self-employed",
  company: "Company",
};

export const MARITAL_LABEL: Record<MaritalStatus, string> = {
  single: "Single",
  married: "Married",
  separated: "Separated",
  divorced: "Divorced",
  widowed: "Widowed",
  not_applicable: "Company / not applicable",
};

export const STATUS_LABEL: Record<ApplicationStatus, string> = {
  started: "Started",
  documents: "Collecting documents",
  in_review: "With finance",
  approved: "Approved",
  declined: "Declined",
  withdrawn: "Withdrawn",
};

export const STATUS_VARIANT: Record<
  ApplicationStatus,
  "info" | "warning" | "success" | "destructive" | "outline"
> = {
  started: "info",
  documents: "warning",
  in_review: "info",
  approved: "success",
  declined: "destructive",
  withdrawn: "outline",
};

/** Basis points as a percentage: 650 → "6.5%". */
export function percent(bp: number): string {
  return `${(bp / 100).toLocaleString("en-GB", { maximumFractionDigits: 2 })}%`;
}

/** "60" months → "5 years"; "42" → "3½ years". */
export function termLabel(months: number): string {
  if (months < 12) return `${months} months`;
  const years = months / 12;
  if (Number.isInteger(years)) return `${years} year${years === 1 ? "" : "s"}`;
  return `${Math.floor(years)}½ years`;
}

/** A percentage typed by an owner ("6.5") to basis points (650), or "invalid". */
export function bpFrom(value: string): number | null | "invalid" {
  const clean = value.replace(/[%\s]/g, "");
  if (clean === "") return null;
  if (!/^\d+(\.\d{1,2})?$/.test(clean)) return "invalid";
  return Math.round(Number(clean) * 100);
}
