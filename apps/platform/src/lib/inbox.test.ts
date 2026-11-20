import { describe, expect, it } from "vitest";

import {
  composeKinds,
  DELIVERY_LABEL,
  deliveryBlocksAddress,
  previewTemplate,
  replyWindow,
  templateUnusableReason,
  type WhatsAppTemplate,
  WHATSAPP_STATUS_LABEL,
} from "./inbox";

describe("composeKinds", () => {
  it("never offers to log a reply on email", () => {
    expect(composeKinds("email")).toEqual(["customer", "note"]);
  });

  it("never offers to log a reply on WhatsApp", () => {
    expect(composeKinds("whatsapp")).toEqual(["customer", "note"]);
  });

  it("keeps logging replies on manual channels", () => {
    expect(composeKinds("manual")).toContain("reply");
  });
});

describe("delivery status", () => {
  it("has a label for every status", () => {
    expect(Object.keys(DELIVERY_LABEL)).toHaveLength(7);
  });

  it("warns that bounces, complaints and suppressions block the address", () => {
    expect(deliveryBlocksAddress("bounced")).toBe(true);
    expect(deliveryBlocksAddress("complained")).toBe(true);
    expect(deliveryBlocksAddress("suppressed")).toBe(true);
    expect(deliveryBlocksAddress("delivered")).toBe(false);
    expect(deliveryBlocksAddress("delayed")).toBe(false);
  });
});

describe("the WhatsApp reply window", () => {
  const now = new Date("2026-11-20T12:00:00Z");

  it("is open until the time the API gives", () => {
    expect(replyWindow("2026-11-20T12:00:01Z", now)).toEqual({
      open: true,
      closesAt: "2026-11-20T12:00:01Z",
    });
  });

  it("is closed at that time, or with no customer message", () => {
    expect(replyWindow("2026-11-20T12:00:00Z", now)).toEqual({ open: false });
    expect(replyWindow(null, now)).toEqual({ open: false });
  });
});

describe("WhatsApp templates", () => {
  const template: WhatsAppTemplate = {
    id: "t1",
    channel_id: "c1",
    name: "follow_up",
    language: "en",
    category: "utility",
    status: "approved",
    body: "Hello {{1}}, the {{2}} is in. {{1}}, reply here.",
    param_count: 2,
    usable: true,
    synced_at: "2026-11-20T12:00:00Z",
  };

  it("previews the values typed so far and keeps the gaps visible", () => {
    expect(previewTemplate(template.body!, ["Clara", ""])).toBe(
      "Hello Clara, the {{2}} is in. Clara, reply here.",
    );
    expect(previewTemplate(template.body!, [" Clara ", "Golf"])).toBe(
      "Hello Clara, the Golf is in. Clara, reply here.",
    );
  });

  it("says why a template cannot be used", () => {
    expect(templateUnusableReason(template)).toBeNull();
    const off = { ...template, usable: false };
    expect(templateUnusableReason({ ...off, status: "paused" })).toMatch(/Not approved/);
    expect(templateUnusableReason({ ...off, category: "marketing" })).toMatch(/consent/);
    expect(templateUnusableReason(off)).toMatch(/not support/);
  });

  it("has a label for every send status", () => {
    expect(Object.keys(WHATSAPP_STATUS_LABEL)).toHaveLength(5);
  });
});
