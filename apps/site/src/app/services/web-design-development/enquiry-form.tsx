"use client";

import { Button } from "@onyx/ui/components/button";
import { useActionState, useState } from "react";

import { webDesignPackages } from "@/content/web-design";

import { sendWebEnquiry } from "./actions";
import { EnquiryCampaignField } from "./campaign-contact";
import { emptyEnquiry, enquiryFields, type EnquiryState, type EnquiryValues } from "./enquiry";

const fieldClass =
  "focus-visible:ring-ring/60 w-full rounded-lg border border-white/20 bg-background px-3 py-2.5 text-base focus-visible:ring-2 focus-visible:outline-none";

export function EnquiryForm() {
  const [state, submit, pending] = useActionState<EnquiryState, FormData>(sendWebEnquiry, {
    status: "idle",
    message: "",
  });
  const [values, setValues] = useState(emptyEnquiry);

  function update(field: keyof EnquiryValues, value: string) {
    setValues((current) => ({ ...current, [field]: value }));
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-white/[0.035] p-5 sm:p-8">
      <p role="status" className={state.status === "sent" ? "text-lg" : "sr-only"}>
        {state.status === "sent" && state.message}
      </p>
      {state.status !== "sent" && (
        <form action={submit} className="grid gap-5" aria-label="Web project enquiry">
          <EnquiryCampaignField />
          <fieldset disabled={pending} className="grid min-w-0 gap-5">
            <div className="grid gap-4 sm:grid-cols-2">
              <label className="grid gap-2 text-sm">
                Name
                <input
                  className={fieldClass}
                  name="name"
                  autoComplete="name"
                  required
                  maxLength={enquiryFields.name}
                  value={values.name}
                  onChange={(event) => update("name", event.target.value)}
                />
              </label>
              <label className="grid gap-2 text-sm">
                Email
                <input
                  className={fieldClass}
                  name="email"
                  type="email"
                  autoComplete="email"
                  required
                  maxLength={enquiryFields.email}
                  value={values.email}
                  onChange={(event) => update("email", event.target.value)}
                />
              </label>
              <label className="grid gap-2 text-sm">
                <span>
                  Business <span className="text-muted-foreground">(optional)</span>
                </span>
                <input
                  className={fieldClass}
                  name="business"
                  autoComplete="organization"
                  maxLength={enquiryFields.business}
                  value={values.business}
                  onChange={(event) => update("business", event.target.value)}
                />
              </label>
              <label className="grid gap-2 text-sm">
                <span>
                  Package <span className="text-muted-foreground">(optional)</span>
                </span>
                <select
                  className={fieldClass}
                  name="package"
                  value={values.package}
                  onChange={(event) => update("package", event.target.value)}
                >
                  <option value="">Help me choose</option>
                  {webDesignPackages.map(({ name }) => (
                    <option key={name} value={name}>
                      {name}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="grid gap-2 text-sm">
              Project brief
              <textarea
                className={`${fieldClass} resize-y`}
                name="brief"
                rows={5}
                required
                maxLength={enquiryFields.brief}
                value={values.brief}
                onChange={(event) => update("brief", event.target.value)}
              />
            </label>
            <div hidden>
              <label>
                Leave this field empty
                <input name="companyWebsite" autoComplete="off" tabIndex={-1} />
              </label>
            </div>
            <p className="text-muted-foreground text-sm">
              We use these details to respond to your enquiry. Read our{" "}
              <a className="text-foreground underline underline-offset-4" href="/privacy">
                privacy policy
              </a>
              .
            </p>
            {state.status === "error" && (
              <p role="alert" className="text-sm">
                {state.message}
              </p>
            )}
            <Button type="submit" variant="brand" className="w-fit rounded-full px-6">
              {pending ? "Sending…" : "Send enquiry"}
            </Button>
          </fieldset>
        </form>
      )}
    </div>
  );
}
