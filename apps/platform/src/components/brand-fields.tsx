"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { useState } from "react";

import { contrastWithWhite, MIN_BRAND_CONTRAST } from "@/lib/tenants";

/**
 * A brand colour with a preview of white text on it. The contrast shown is a hint; the API
 * refuses colours below 4.5:1 whatever this says.
 */
export function BrandColorField({
  id,
  error,
  defaultValue = "",
  name = "brand_color",
}: {
  id: string;
  error?: string;
  defaultValue?: string;
  name?: string;
}) {
  const [color, setColor] = useState(defaultValue);
  const ratio = contrastWithWhite(color);
  return (
    <FormField
      id={id}
      label="Brand colour"
      hint="Optional, as #rrggbb. White text sits on it, so it must be dark enough to read."
      error={error}
    >
      <div className="flex flex-wrap items-center gap-3">
        <Input
          id={id}
          name={name}
          value={color}
          onChange={(e) => setColor(e.target.value.trim())}
          placeholder="#1f4e79"
          maxLength={7}
          className="w-32 font-mono"
        />
        <input
          type="color"
          aria-label="Pick a brand colour"
          value={ratio === null ? "#1f4e79" : color}
          onChange={(e) => setColor(e.target.value)}
          className="h-9 w-12 cursor-pointer rounded border"
        />
        {ratio !== null ? (
          <span
            className="rounded px-3 py-1.5 text-sm font-medium text-white"
            style={{ backgroundColor: color }}
          >
            Sample text
          </span>
        ) : null}
        {ratio !== null ? (
          <span
            className={
              ratio >= MIN_BRAND_CONTRAST
                ? "text-muted-foreground text-xs"
                : "text-destructive text-xs"
            }
          >
            Contrast {ratio.toFixed(1)}:1
            {ratio >= MIN_BRAND_CONTRAST ? "" : ", too light: choose a darker colour"}
          </span>
        ) : null}
      </div>
    </FormField>
  );
}

/** A one-time link, selectable, with a copy button. */
export function CopyLink({ link, label }: { link: string; label: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <FormField id="invite-link" label={label}>
      <div className="flex flex-wrap items-center gap-2">
        <Input id="invite-link" readOnly value={link} className="flex-1 font-mono text-xs" />
        <Button
          type="button"
          variant="outline"
          onClick={() => {
            void navigator.clipboard?.writeText(link).then(() => setCopied(true));
          }}
        >
          {copied ? "Copied" : "Copy link"}
        </Button>
      </div>
    </FormField>
  );
}
