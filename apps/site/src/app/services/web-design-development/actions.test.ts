import { afterEach, describe, expect, it, vi } from "vitest";

import { sendWebEnquiry } from "./actions";

const initialState = { status: "idle", message: "" } as const;

function validEnquiry() {
  const form = new FormData();
  form.set("name", "Test Visitor");
  form.set("email", "visitor@example.com");
  form.set("package", "Silver");
  form.set("brief", "We need a website for our fictional business.");
  return form;
}

afterEach(() => {
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

describe("website enquiries", () => {
  it("sends a plain-text enquiry to the fixed studio inbox and deduplicates retries", async () => {
    vi.stubEnv("ONYX_SITE_RESEND_API_KEY", "fake-key");
    const send = vi.fn<typeof fetch>().mockResolvedValue(new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", send);

    const form = validEnquiry();
    expect(await sendWebEnquiry(initialState, form)).toMatchObject({ status: "sent" });
    expect(await sendWebEnquiry(initialState, form)).toMatchObject({ status: "sent" });

    const [url, request] = send.mock.calls[0]!;
    expect(url).toBe("https://api.resend.com/emails");
    expect(JSON.parse(request?.body as string)).toMatchObject({
      to: ["info@onyx.mt"],
      reply_to: "visitor@example.com",
      text: expect.stringContaining("Package: Silver"),
    });
    const key = new Headers(request?.headers).get("Idempotency-Key");
    expect(key).toMatch(/^studio-web-enquiry\/[a-f0-9]{64}$/);
    expect(new Headers(send.mock.calls[1]?.[1]?.headers).get("Idempotency-Key")).toBe(key);
  });

  it.each([
    ["email", "visitor@example.com,other@example.com"],
    ["package", "Unknown"],
    ["brief", "x".repeat(3001)],
    ["name", ""],
  ])("rejects invalid %s before calling the provider", async (field, value) => {
    vi.stubEnv("ONYX_SITE_RESEND_API_KEY", "fake-key");
    const send = vi.fn();
    vi.stubGlobal("fetch", send);
    const form = validEnquiry();
    form.set(field, value);

    expect(await sendWebEnquiry(initialState, form)).toMatchObject({ status: "error" });
    expect(send).not.toHaveBeenCalled();
  });

  it("silently discards requests caught by the spam trap", async () => {
    vi.stubEnv("ONYX_SITE_RESEND_API_KEY", "fake-key");
    const send = vi.fn();
    vi.stubGlobal("fetch", send);
    const form = validEnquiry();
    form.set("companyWebsite", "https://example.com");

    expect(await sendWebEnquiry(initialState, form)).toMatchObject({ status: "sent" });
    expect(send).not.toHaveBeenCalled();
  });

  it("keeps contact options actionable when sending is unconfigured", async () => {
    vi.stubEnv("ONYX_SITE_RESEND_API_KEY", "");
    const send = vi.fn();
    vi.stubGlobal("fetch", send);

    expect(await sendWebEnquiry(initialState, validEnquiry())).toMatchObject({
      status: "error",
      message: expect.stringContaining("direct contact options"),
    });
    expect(send).not.toHaveBeenCalled();
  });

  it("returns the same retry message on provider errors and timeouts", async () => {
    vi.stubEnv("ONYX_SITE_RESEND_API_KEY", "fake-key");
    const send = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(new Response(null, { status: 429 }))
      .mockRejectedValueOnce(new DOMException("Timed out", "TimeoutError"));
    vi.stubGlobal("fetch", send);

    const rejected = await sendWebEnquiry(initialState, validEnquiry());
    expect(rejected).toMatchObject({ status: "error" });
    expect(await sendWebEnquiry(initialState, validEnquiry())).toEqual(rejected);
  });
});
