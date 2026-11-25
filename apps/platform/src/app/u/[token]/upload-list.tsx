"use client";

import { Button } from "@onyx/ui/components/button";
import { CircleCheck, Upload } from "lucide-react";
import { useRef, useState, useTransition } from "react";

export type UploadPage = {
  business_name: string;
  expires_at: string;
  needed: {
    id: string;
    label: string;
    note: string | null;
    rejected_reason: string | null;
    form_kind?: string | null;
  }[];
  received: number;
};

const MAX_BYTES = 10 * 1024 * 1024;

async function toBase64(file: Blob): Promise<string> {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  for (let i = 0; i < bytes.length; i += 0x8000) {
    binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
  }
  return btoa(binary);
}

/** The documents still needed; each uploads straight to the Onyx API with the link's token. */
export function UploadList({
  token,
  apiUrl,
  initial,
}: {
  token: string;
  apiUrl: string;
  initial: UploadPage;
}) {
  const [page, setPage] = useState(initial);
  const [justSent, setJustSent] = useState<string | null>(null);
  const done = page.needed.length === 0;
  return (
    <>
      <div className="flex flex-col gap-2">
        <h1 className="text-2xl font-light tracking-tight">
          {done ? "Thank you, that's everything" : "Upload your documents"}
        </h1>
        <p className="text-muted-foreground text-sm">
          {done
            ? `${page.business_name} has what they need and will check it. You can close this page.`
            : `${page.business_name} needs the documents below. Take a clear photo or upload a PDF (up to 10 MB each).`}
        </p>
      </div>
      {justSent ? (
        <p
          role="status"
          className="border-success/30 bg-success/[0.06] flex items-center gap-2 rounded-xl border px-4 py-3 text-sm"
        >
          <CircleCheck aria-hidden className="text-success size-4" />
          {justSent} received.
        </p>
      ) : null}
      <ul className="flex flex-col gap-3" aria-label="Documents needed">
        {page.needed.map((item) => (
          <li key={item.id}>
            <Item
              token={token}
              apiUrl={apiUrl}
              item={item}
              onDone={(next) => {
                setPage(next);
                setJustSent(item.label);
              }}
            />
          </li>
        ))}
      </ul>
      {page.received > 0 && !done ? (
        <p className="text-muted-foreground text-sm">
          {page.received} document{page.received === 1 ? "" : "s"} already received.
        </p>
      ) : null}
    </>
  );
}

function Item({
  token,
  apiUrl,
  item,
  onDone,
}: {
  token: string;
  apiUrl: string;
  item: UploadPage["needed"][number];
  onDone: (page: UploadPage) => void;
}) {
  const input = useRef<HTMLInputElement>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, start] = useTransition();

  function send(file: File | undefined) {
    if (!file) return;
    setError(null);
    if (file.size > MAX_BYTES) {
      setError("This file is over 10 MB. Try a smaller photo or scan.");
      return;
    }
    start(async () => {
      try {
        const response = await fetch(`${apiUrl}/v1/public/uploads/${token}/documents/${item.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            filename: file.name.slice(0, 255) || "document",
            content_base64: await toBase64(file),
          }),
        });
        if (response.ok) {
          onDone((await response.json()) as UploadPage);
          return;
        }
        const body = (await response.json().catch(() => null)) as {
          error?: { message?: string };
        } | null;
        setError(
          response.status === 422
            ? "Please upload a photo (JPEG, PNG or HEIC) or a PDF."
            : (body?.error?.message ?? "The upload failed. Please try again."),
        );
      } catch {
        setError("The upload failed. Check your connection and try again.");
      } finally {
        if (input.current) input.current.value = "";
      }
    });
  }

  return (
    <div className="bg-card flex flex-col gap-3 rounded-2xl border p-4">
      <div className="flex flex-col gap-1">
        <p className="font-medium">{item.label}</p>
        {item.note ? <p className="text-muted-foreground text-sm">{item.note}</p> : null}
        {item.form_kind ? (
          <a
            className="text-brand self-start text-sm underline-offset-4 hover:underline"
            href={`${apiUrl}/v1/public/uploads/${token}/forms/${item.form_kind}`}
          >
            Download the blank form, fill it in and upload it here
          </a>
        ) : null}
        {item.rejected_reason ? (
          <p className="text-destructive text-sm">Please send it again: {item.rejected_reason}</p>
        ) : null}
      </div>
      <input
        ref={input}
        id={`file-${item.id}`}
        type="file"
        accept="image/*,application/pdf,.heic"
        className="sr-only"
        aria-label={`Choose a file for ${item.label}`}
        onChange={(e) => send(e.target.files?.[0])}
      />
      <Button
        type="button"
        disabled={pending}
        onClick={() => input.current?.click()}
        className="self-start"
      >
        <Upload aria-hidden />
        {pending ? "Uploading…" : "Take a photo or choose a file"}
      </Button>
      {error ? (
        <p role="alert" className="text-destructive text-sm">
          {error}
        </p>
      ) : null}
    </div>
  );
}
