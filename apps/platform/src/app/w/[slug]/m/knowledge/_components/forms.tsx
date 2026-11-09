"use client";

import { Button } from "@onyx/ui/components/button";
import { FormField } from "@onyx/ui/components/form-field";
import { Input } from "@onyx/ui/components/input";
import Link from "next/link";
import { useActionState, useEffect, useRef, useState } from "react";

import { IDLE } from "@/lib/form-state";
import { ACCEPT, fileProblem, knowledgePath } from "@/lib/knowledge";

import { FormStatus } from "../../../settings/form-status";
import { deleteDocument, replaceDocument, type UploadState, uploadDocument } from "../actions";

/** The chosen file, checked in the browser first; the API checks it again regardless. */
function FileField({
  id,
  label,
  error,
  disabled,
}: {
  id: string;
  label: string;
  error?: string;
  disabled: boolean;
}) {
  const [problem, setProblem] = useState<string | null>(null);
  return (
    <FormField
      id={id}
      label={label}
      hint="PDF, .txt or .md, up to 4 MB. Scanned PDFs without text cannot be read."
      error={problem ?? error}
    >
      <Input
        id={id}
        name="file"
        type="file"
        accept={ACCEPT}
        required
        disabled={disabled}
        onChange={(e) => {
          const file = e.currentTarget.files?.[0];
          const message = file ? fileProblem(file.name, file.size) : null;
          setProblem(message);
          e.currentTarget.setCustomValidity(message ?? "");
        }}
      />
    </FormField>
  );
}

function Duplicate({ slug, state }: { slug: string; state: UploadState }) {
  if (!state.existingId) return null;
  return (
    <p className="text-sm">
      <Link
        className="underline underline-offset-4"
        href={knowledgePath(slug, "documents", state.existingId)}
      >
        Open the existing document
      </Link>{" "}
      to replace its file instead.
    </p>
  );
}

export function UploadDocumentForm({ slug }: { slug: string }) {
  const [state, action, pending] = useActionState(
    uploadDocument.bind(null, slug),
    IDLE as UploadState,
  );
  return (
    <form action={action} className="flex max-w-md flex-col gap-3">
      <FormStatus state={state} />
      <Duplicate slug={slug} state={state} />
      <FormField id="document-title" label="Title" error={state.fieldErrors?.title}>
        <Input id="document-title" name="title" required maxLength={200} disabled={pending} />
      </FormField>
      <FileField
        id="document-file"
        label="File"
        error={state.fieldErrors?.file}
        disabled={pending}
      />
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Indexing…" : "Upload document"}
      </Button>
    </form>
  );
}

export function ReplaceDocumentForm({
  slug,
  documentId,
  title,
}: {
  slug: string;
  documentId: string;
  title: string;
}) {
  const [state, action, pending] = useActionState(
    replaceDocument.bind(null, slug, documentId),
    IDLE as UploadState,
  );
  const form = useRef<HTMLFormElement>(null);
  useEffect(() => {
    if (state.status === "ok") form.current?.reset();
  }, [state]);
  return (
    <form ref={form} action={action} className="flex max-w-md flex-col gap-3">
      <FormStatus state={state} />
      <Duplicate slug={slug} state={state} />
      <FileField
        id="replace-file"
        label="New file"
        error={state.fieldErrors?.file}
        disabled={pending}
      />
      <FormField
        id="replace-title"
        label="New title"
        hint="Optional. Leave blank to keep the current title."
        error={state.fieldErrors?.title}
      >
        <Input
          id="replace-title"
          name="title"
          maxLength={200}
          placeholder={title}
          disabled={pending}
        />
      </FormField>
      <Button type="submit" disabled={pending} className="self-start">
        {pending ? "Indexing…" : "Replace file"}
      </Button>
    </form>
  );
}

export function DeleteDocumentForm({
  slug,
  documentId,
  title,
}: {
  slug: string;
  documentId: string;
  title: string;
}) {
  const [state, action, pending] = useActionState(
    deleteDocument.bind(null, slug, documentId),
    IDLE,
  );
  return (
    <form
      action={action}
      className="flex flex-col gap-2"
      onSubmit={(e) => {
        const ok = window.confirm(
          `Delete "${title}"? Staff and the assistant will no longer find it. This cannot be undone.`,
        );
        if (!ok) e.preventDefault();
      }}
    >
      <FormStatus state={state} />
      <Button type="submit" variant="destructive" disabled={pending} className="self-start">
        {pending ? "Deleting…" : "Delete document"}
      </Button>
    </form>
  );
}
