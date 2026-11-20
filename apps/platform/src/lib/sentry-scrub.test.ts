import { describe, expect, it } from "vitest";

import { beforeSend, REDACTED, scrubText } from "./sentry-scrub";

describe("scrubText", () => {
  it("removes contact details, tokens and keys", () => {
    const text = scrubText(
      "clara.borg@seaview.example.test called +356 2100 0001; Bearer abc.def; re_live_abcdefgh123",
    );
    expect(text).not.toMatch(/clara|2100|abc\.def|re_live/);
    expect(text).toContain(REDACTED);
  });

  it("keeps the name of an invitation token parameter, not its value", () => {
    expect(scrubText("/invitations/accept?token=s3cret-value")).toBe(
      `/invitations/accept?token=${REDACTED}`,
    );
  });

  it("leaves ordinary text alone", () => {
    expect(scrubText("Quote 42 failed to render")).toBe("Quote 42 failed to render");
  });
});

describe("beforeSend", () => {
  it("drops request bodies, headers, cookies, query strings and the user", () => {
    const event = beforeSend({
      request: {
        url: "https://app.onyx.test/w/lumen?token=x",
        headers: { authorization: "Bearer y" },
        cookies: { sb: "z" },
        data: "body",
        query_string: "token=x",
      },
      user: { email: "mia@lumen.example.test" },
      server_name: "laptop",
      message: "failed for mia@lumen.example.test",
    });
    expect(event.request).toEqual({ url: "https://app.onyx.test/w/lumen" });
    expect(event.user).toBeUndefined();
    expect(event.server_name).toBeUndefined();
    expect(event.message).toBe(`failed for ${REDACTED}`);
  });
});
