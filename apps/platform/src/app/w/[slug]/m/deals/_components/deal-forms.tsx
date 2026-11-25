"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import { selectClass } from "@onyx/ui/lib/form-classes";
import { Upload } from "lucide-react";
import { useRouter } from "next/navigation";
import { useActionState, useRef, useState, useTransition } from "react";

import { DEPOSIT_METHOD_LABEL, type DealStage, type DepositMethod, STAGE_LABEL } from "@/lib/deals";
import { type FormState, IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import {
  addDocument,
  changeStage,
  checkDocument,
  recordDeposit,
  updateDeal,
  uploadDocument,
} from "../actions";

export function StageForm({
  slug,
  dealId,
  stages,
  canOverride,
}: {
  slug: string;
  dealId: string;
  stages: DealStage[];
  canOverride: boolean;
}) {
  const [state, action, pending] = useActionState(changeStage.bind(null, slug, dealId), IDLE);
  const [target, setTarget] = useState<DealStage | "">("");
  const needsReason = target === "cancelled" || (target === "sold" && canOverride);
  return (
    <form action={action} className="flex flex-col gap-3" noValidate aria-label="Change stage">
      <FormStatus state={state} />
      <div className="flex flex-wrap items-end gap-3">
        <FormField id="deal-stage" label="Move to" className="w-56">
          <select
            id="deal-stage"
            name="stage"
            value={target}
            onChange={(e) => setTarget(e.target.value as DealStage)}
            className={selectClass}
          >
            <option value="">Choose a stage</option>
            {stages.map((s) => (
              <option key={s} value={s}>
                {STAGE_LABEL[s]}
              </option>
            ))}
          </select>
        </FormField>
        <Button type="submit" disabled={pending || target === ""}>
          {pending ? "Saving…" : "Update stage"}
        </Button>
      </div>
      {needsReason ? (
        <FormField
          id="deal-reason"
          label={target === "cancelled" ? "Why is it cancelled?" : "Reason (for an override)"}
          error={state.fieldErrors?.reason}
        >
          <Input id="deal-reason" name="reason" maxLength={500} />
        </FormField>
      ) : null}
      {target === "sold" && canOverride ? (
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" name="override" className="accent-brand mt-0.5 size-4" />
          <span>
            Mark it sold even if some required documents are not verified yet (owners only, with a
            reason; recorded in the history and audit log).
          </span>
        </label>
      ) : null}
    </form>
  );
}

export function DepositForm({ slug, dealId }: { slug: string; dealId: string }) {
  const [state, action, pending] = useActionState(recordDeposit.bind(null, slug, dealId), IDLE);
  const errors = state.fieldErrors ?? {};
  const today = new Date().toISOString().slice(0, 10);
  return (
    <form action={action} className="flex flex-col gap-3" noValidate aria-label="Record deposit">
      <FormStatus state={state} />
      <div className="grid gap-3 sm:grid-cols-3">
        <FormField
          id="deposit-amount"
          label="Amount (€)"
          error={errors.amount ?? errors.amount_cents}
        >
          <Input id="deposit-amount" name="amount" inputMode="decimal" required />
        </FormField>
        <FormField id="deposit-date" label="Received on" error={errors.received_on}>
          <Input id="deposit-date" name="received_on" type="date" defaultValue={today} required />
        </FormField>
        <FormField id="deposit-method" label="Method" error={errors.method}>
          <select id="deposit-method" name="method" className={selectClass} defaultValue="card">
            {(Object.keys(DEPOSIT_METHOD_LABEL) as DepositMethod[]).map((m) => (
              <option key={m} value={m}>
                {DEPOSIT_METHOD_LABEL[m]}
              </option>
            ))}
          </select>
        </FormField>
      </div>
      <Button type="submit" variant="secondary" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Record deposit"}
      </Button>
    </form>
  );
}

export function SaleOptionsForm({
  slug,
  dealId,
  financed,
  hasTradeIn,
}: {
  slug: string;
  dealId: string;
  financed: boolean;
  hasTradeIn: boolean;
}) {
  const [state, action, pending] = useActionState(updateDeal.bind(null, slug, dealId), IDLE);
  return (
    <form action={action} className="flex flex-col gap-3" noValidate aria-label="Sale options">
      <FormStatus state={state} />
      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          name="financed"
          defaultChecked={financed}
          className="accent-brand size-4"
        />
        Financed in-house
      </label>
      <label className="flex items-center gap-3 text-sm">
        <input
          type="checkbox"
          name="has_trade_in"
          defaultChecked={hasTradeIn}
          className="accent-brand size-4"
        />
        Includes a trade-in
      </label>
      <Button type="submit" variant="secondary" size="sm" disabled={pending} className="self-start">
        {pending ? "Saving…" : "Save"}
      </Button>
    </form>
  );
}

export function AddDocumentForm({ slug, dealId }: { slug: string; dealId: string }) {
  const [state, action, pending] = useActionState(addDocument.bind(null, slug, dealId), IDLE);
  return (
    <form
      action={action}
      className="flex flex-wrap items-end gap-3"
      noValidate
      aria-label="Add a document"
    >
      <FormStatus state={state} />
      <FormField
        id="doc-label"
        label="Another document"
        className="min-w-56 flex-1"
        error={state.fieldErrors?.label}
      >
        <Input
          id="doc-label"
          name="label"
          maxLength={100}
          placeholder="e.g. Insurance cover note"
        />
      </FormField>
      <label className="flex items-center gap-2 pb-2 text-sm">
        <input type="checkbox" name="required" defaultChecked className="accent-brand size-4" />
        Required
      </label>
      <Button type="submit" variant="secondary" disabled={pending}>
        {pending ? "Adding…" : "Add"}
      </Button>
    </form>
  );
}

export function CheckDocumentForm({
  slug,
  dealId,
  documentId,
  label,
}: {
  slug: string;
  dealId: string;
  documentId: string;
  label: string;
}) {
  const [state, action, pending] = useActionState(
    checkDocument.bind(null, slug, dealId, documentId),
    IDLE,
  );
  const [rejecting, setRejecting] = useState(false);
  return (
    <form action={action} className="flex flex-col gap-2" noValidate aria-label={`Check ${label}`}>
      <FormStatus state={state} />
      {rejecting ? (
        <div className="flex flex-wrap items-end gap-2">
          <FormField
            id={`reason-${documentId}`}
            label="Why is it rejected?"
            className="min-w-56 flex-1"
          >
            <Input
              id={`reason-${documentId}`}
              name="reason"
              maxLength={300}
              placeholder="e.g. Blurred photo"
              required
            />
          </FormField>
          <Button
            type="submit"
            name="verdict"
            value="reject"
            variant="destructive"
            size="sm"
            disabled={pending}
          >
            Reject
          </Button>
          <Button type="button" variant="ghost" size="sm" onClick={() => setRejecting(false)}>
            Back
          </Button>
        </div>
      ) : (
        <div className="flex gap-2">
          <Button type="submit" name="verdict" value="verify" size="sm" disabled={pending}>
            Verify
          </Button>
          <Button type="button" variant="outline" size="sm" onClick={() => setRejecting(true)}>
            Reject…
          </Button>
        </div>
      )}
    </form>
  );
}

// Uploads go through the dashboard server (Vercel caps a request at about 4.5 MB), so a large
// photo is resized in the browser first. Customers use the upload link, which takes 10 MB.
const MAX_SEND_BYTES = 3 * 1024 * 1024;
const RESIZE_EDGE = 2400;

async function shrink(file: File): Promise<Blob> {
  if (file.size <= MAX_SEND_BYTES || !["image/jpeg", "image/png"].includes(file.type)) return file;
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, RESIZE_EDGE / Math.max(bitmap.width, bitmap.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(bitmap.width * scale);
  canvas.height = Math.round(bitmap.height * scale);
  canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
  return await new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("resize"))), "image/jpeg", 0.85),
  );
}

async function toBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

export function UploadDocument({
  slug,
  dealId,
  documentId,
  label,
  replace,
}: {
  slug: string;
  dealId: string;
  documentId: string;
  label: string;
  replace: boolean;
}) {
  const input = useRef<HTMLInputElement>(null);
  const router = useRouter();
  const [state, setState] = useState<FormState>(IDLE);
  const [pending, start] = useTransition();

  function onFile(file: File | undefined) {
    if (!file) return;
    start(async () => {
      try {
        const blob = await shrink(file);
        if (blob.size > MAX_SEND_BYTES) {
          setState({
            status: "error",
            message:
              "This file is over 3 MB. Scan it smaller, or send the customer the upload link.",
          });
          return;
        }
        const name = blob === file ? file.name : file.name.replace(/\.\w+$/, "") + ".jpg";
        const result = await uploadDocument(slug, dealId, documentId, {
          filename: name.slice(0, 255),
          content_base64: await toBase64(blob),
        });
        setState(result);
        if (result.status === "ok") router.refresh();
      } catch {
        setState({ status: "error", message: "The file could not be read. Try again." });
      } finally {
        if (input.current) input.current.value = "";
      }
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <input
        ref={input}
        id={`file-${documentId}`}
        type="file"
        accept="application/pdf,image/jpeg,image/png,image/heic,.heic"
        className="sr-only"
        onChange={(e) => onFile(e.target.files?.[0])}
        aria-label={`Upload ${label}`}
      />
      <Button
        type="button"
        variant="secondary"
        size="sm"
        disabled={pending}
        onClick={() => input.current?.click()}
        className="self-start"
      >
        <Upload aria-hidden />
        {pending ? "Uploading…" : replace ? "Replace file" : "Upload"}
      </Button>
      {state.status === "error" ? <FormStatus state={state} /> : null}
    </div>
  );
}
