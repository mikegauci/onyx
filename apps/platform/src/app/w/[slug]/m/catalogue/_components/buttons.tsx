"use client";

import { Button } from "@onyx/ui/components/button";
import { useActionState } from "react";

import { IDLE } from "@/lib/form-state";

import { FormStatus } from "../../../settings/form-status";
import {
  makeDefaultPriceList,
  setProductArchived,
  setVariantArchived,
  setVatRateArchived,
} from "../actions";

type Kind = "product" | "variant" | "vat";
const LABEL: Record<Kind, string> = { product: "product", variant: "SKU", vat: "VAT rate" };

/** Archive or restore a product, SKU or VAT rate. */
export function ArchiveButton({
  slug,
  kind,
  id,
  archived,
  name,
}: {
  slug: string;
  kind: Kind;
  id: string;
  archived: boolean;
  name?: string;
}) {
  const action =
    kind === "product"
      ? setProductArchived.bind(null, slug, id, !archived)
      : kind === "variant"
        ? setVariantArchived.bind(null, slug, id, !archived)
        : setVatRateArchived.bind(null, slug, id, !archived);
  const [state, formAction, pending] = useActionState(action, IDLE);
  const verb = archived ? "Restore" : "Archive";
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button
        type="submit"
        variant="outline"
        size={kind === "product" ? "default" : "sm"}
        disabled={pending}
        className="self-start"
        aria-label={name ? `${verb} ${LABEL[kind]} ${name}` : undefined}
      >
        {`${verb} ${LABEL[kind]}`}
      </Button>
    </form>
  );
}

export function MakeDefaultButton({ slug, id, code }: { slug: string; id: string; code: string }) {
  const [state, formAction, pending] = useActionState(
    makeDefaultPriceList.bind(null, slug, id),
    IDLE,
  );
  return (
    <form action={formAction} className="flex flex-col gap-2">
      <FormStatus state={state} />
      <Button
        type="submit"
        variant="outline"
        size="sm"
        disabled={pending}
        className="self-start"
        aria-label={`Make ${code} the default price list`}
      >
        Make default
      </Button>
    </form>
  );
}
