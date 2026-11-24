"use server";

import { createHmac } from "node:crypto";

import { site } from "@/content/site";
import { webDesignPackages } from "@/content/web-design";

import { emptyEnquiry, enquiryFields, type EnquiryState, type EnquiryValues } from "./enquiry";

const unavailable: EnquiryState = {
  status: "error",
  message: "We couldn't send your enquiry. Try again or use one of the direct contact options.",
};

export async function sendWebEnquiry(
  _previous: EnquiryState,
  formData: FormData,
): Promise<EnquiryState> {
  const sent: EnquiryState = { status: "sent", message: "Thanks. Your enquiry has been sent." };

  // A field hidden from visitors catches bots that fill every input.
  if (formData.get("companyWebsite")) return sent;

  const values = { ...emptyEnquiry };
  for (const field of Object.keys(enquiryFields) as (keyof EnquiryValues)[]) {
    const value = formData.get(field);
    if (value !== null && (typeof value !== "string" || value.length > enquiryFields[field])) {
      return { status: "error", message: "Please check the length of your enquiry and try again." };
    }
    values[field] = typeof value === "string" ? value.trim() : "";
  }

  if (
    !values.name ||
    !/^[^\s@<>,;]+@[^\s@<>,;]+\.[^\s@<>,;]+$/u.test(values.email) ||
    !values.brief
  ) {
    return {
      status: "error",
      message: "Enter your name, a valid email and a short project brief.",
    };
  }

  if (values.package && !webDesignPackages.some(({ name }) => name === values.package)) {
    return { status: "error", message: "Choose a package from the list or leave it blank." };
  }

  const apiKey = process.env.ONYX_SITE_RESEND_API_KEY?.trim();
  if (!apiKey) return unavailable;

  // Resend deduplicates identical enquiries for 24 hours, including retries after a timeout.
  const digest = createHmac("sha256", apiKey).update(JSON.stringify(values)).digest("hex");

  try {
    const response = await fetch("https://api.resend.com/emails", {
      method: "POST",
      headers: {
        Authorization: `Bearer ${apiKey}`,
        "Content-Type": "application/json",
        "Idempotency-Key": `studio-web-enquiry/${digest}`,
      },
      body: JSON.stringify({
        from: "Onyx Studio Website <website@reply.onyx.mt>",
        to: [site.contactEmail],
        reply_to: values.email,
        subject: "New Onyx Studio web project enquiry",
        text: [
          `Name: ${values.name}`,
          `Email: ${values.email}`,
          `Business: ${values.business || "Not supplied"}`,
          `Package: ${values.package || "Not selected"}`,
          "",
          values.brief,
        ].join("\n"),
      }),
      signal: AbortSignal.timeout(5000),
      redirect: "error",
    });

    return response.ok ? sent : unavailable;
  } catch {
    return unavailable;
  }
}
