import { describe, expect, it } from "vitest";

import { type Draft, draftControls, isEdited, outboundPath } from "./outbound";

const MEMBER = ["outbound.read", "outbound.write"];
const APPROVER = [...MEMBER, "outbound.approve"];

function draft(overrides: Partial<Draft> = {}): Draft {
  return {
    id: "d1",
    conversation_id: "c1",
    conversation_subject: "Chandelier",
    origin: "staff",
    status: "pending",
    current_revision: 1,
    body: "Hello",
    quote: null,
    expires_at: "2026-11-09T12:00:00Z",
    expiry: null,
    approved_revision: null,
    approved_by: null,
    approved_at: null,
    rejection_reason: null,
    decided_by: null,
    decided_at: null,
    sent_message_id: null,
    sent_by: null,
    sent_at: null,
    created_by: null,
    created_at: "2026-11-06T12:00:00Z",
    updated_at: "2026-11-06T12:00:00Z",
    ...overrides,
  };
}

describe("draftControls", () => {
  it("lets members edit but not approve or send a pending reply", () => {
    const controls = draftControls(draft(), MEMBER);
    expect(controls).toMatchObject({
      canEdit: true,
      canApprove: false,
      canReject: false,
      canSend: false,
      canApproveAndSend: false,
    });
    expect(controls.sendHint).toMatch(/must approve/);
  });

  it("lets approvers approve and reject, and nobody send before approval", () => {
    const controls = draftControls(draft(), APPROVER);
    expect(controls).toMatchObject({ canApprove: true, canReject: true, canSend: false });
    expect(controls.sendHint).toMatch(/Approve the reply/);
  });

  it("blocks approval while the quote is not approved, with the API's message", () => {
    const quote = {
      id: "q1",
      number: "Q-2026-0009",
      status: "draft",
      version: 1,
      approved_version: null,
      blocked: { code: "quote_not_approved" as const, message: "Approve the quote first." },
    };
    const controls = draftControls(draft({ quote }), APPROVER);
    expect(controls.canApprove).toBe(false);
    expect(controls.canApproveAndSend).toBe(false);
    expect(controls.approveHint).toBe("Approve the quote first.");
    expect(controls.sendHint).toBe("Approve the quote first.");
  });

  it("lets approvers approve and send in one step", () => {
    expect(draftControls(draft(), APPROVER).canApproveAndSend).toBe(true);
    expect(draftControls(draft({ status: "approved" }), APPROVER).canApproveAndSend).toBe(true);
    // Approving alone is not enough: sending also needs outbound.write.
    expect(draftControls(draft(), ["outbound.read", "outbound.approve"]).canApproveAndSend).toBe(
      false,
    );
  });

  it("offers sending only for an approved reply", () => {
    expect(draftControls(draft({ status: "approved" }), MEMBER).canSend).toBe(true);
    expect(draftControls(draft({ status: "approved" }), ["outbound.read"]).canSend).toBe(false);
  });

  it.each(["sent", "rejected", "expired", "superseded"] as const)(
    "offers nothing on a %s reply",
    (status) => {
      expect(draftControls(draft({ status }), APPROVER)).toMatchObject({
        canEdit: false,
        canApprove: false,
        canReject: false,
        canSend: false,
        canApproveAndSend: false,
        sendHint: null,
      });
    },
  );
});

describe("isEdited", () => {
  it("ignores surrounding whitespace, as the API does", () => {
    expect(isEdited("Hello", "  Hello \n")).toBe(false);
    expect(isEdited("Hello", "Hello there")).toBe(true);
  });
});

describe("outboundPath", () => {
  it("encodes the slug", () => {
    expect(outboundPath("a b", "drafts", "d1")).toBe("/w/a%20b/m/outbound/drafts/d1");
  });
});
