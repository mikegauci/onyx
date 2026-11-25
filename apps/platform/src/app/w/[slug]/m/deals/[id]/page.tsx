import { Badge } from "@onyx/ui/components/badge";
import { DetailList, Panel } from "@onyx/ui/components/page";
import Link from "next/link";
import { notFound } from "next/navigation";

import { BackLink } from "@/components/back-link";
import { withApi } from "@/lib/api-client";
import { automotivePath, euros } from "@/lib/automotive";
import { crmPath, formatInZone } from "@/lib/crm";
import { getWorkspace } from "@/lib/data";
import {
  DEPOSIT_METHOD_LABEL,
  DOCUMENT_STATE_LABEL,
  DOCUMENT_STATE_VARIANT,
  dealsPath,
  eventLabel,
  nextStages,
  STAGE_LABEL,
  STAGE_VARIANT,
} from "@/lib/deals";
import { requireOk } from "@/lib/guards";
import { inboxPath } from "@/lib/inbox";
import { quotationsPath } from "@/lib/quotations";

import {
  AddDocumentForm,
  CheckDocumentForm,
  DepositForm,
  SaleOptionsForm,
  StageForm,
  UploadDocument,
} from "../_components/deal-forms";

type Props = { params: Promise<{ slug: string; id: string }> };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const LINK = "text-brand underline-offset-4 hover:underline";

export default async function DealPage({ params }: Props) {
  const { slug, id } = await params;
  if (!UUID.test(id)) notFound();
  const path = dealsPath(slug, id);
  const workspace = requireOk(await getWorkspace(slug), path);
  const deal = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/{deal_id}", { params: { path: { slug, deal_id: id } } }),
    ),
    path,
  );
  const zone = workspace.timezone;
  const can = (p: string) => workspace.permissions.includes(p as never);
  const canWrite = can("deals.write");
  const canOpen = can("deals.documents");
  const open = !["sold", "collected", "cancelled"].includes(deal.stage);
  const closed = deal.stage === "collected" || deal.stage === "cancelled";
  const incomplete = deal.documents_verified < deal.documents_total;

  return (
    <>
      <BackLink href={dealsPath(slug, "board")}>Back to deals</BackLink>
      <div className="flex flex-col gap-2">
        <h2 className="flex flex-wrap items-center gap-3 text-2xl font-light tracking-tight">
          {deal.title}
          <Badge variant={STAGE_VARIANT[deal.stage]}>{STAGE_LABEL[deal.stage]}</Badge>
        </h2>
        <p className="text-muted-foreground text-sm">
          Documents {deal.documents_verified} of {deal.documents_total} verified
          {deal.cancel_reason ? ` · Cancelled: ${deal.cancel_reason}` : ""}
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <div className="flex min-w-0 flex-col gap-6">
          <Panel
            title="Documents"
            description={
              canOpen
                ? "Open each file to check it, then verify or reject it."
                : "Upload what the customer gives you. An owner or admin checks each file."
            }
          >
            <ul className="flex flex-col divide-y" aria-label="Checklist">
              {deal.documents.map((doc) => (
                <li
                  key={doc.id}
                  className="flex flex-col gap-3 py-4 first:pt-0 last:pb-0 sm:flex-row sm:items-start sm:justify-between"
                >
                  <div className="flex min-w-0 flex-col gap-1">
                    <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
                      {doc.label}
                      {!doc.required ? (
                        <span className="text-muted-foreground text-xs font-normal">Optional</span>
                      ) : null}
                      <Badge variant={DOCUMENT_STATE_VARIANT[doc.state]}>
                        {DOCUMENT_STATE_LABEL[doc.state]}
                      </Badge>
                    </p>
                    {doc.note ? <p className="text-muted-foreground text-xs">{doc.note}</p> : null}
                    {doc.rejection_reason ? (
                      <p className="text-destructive text-xs">Rejected: {doc.rejection_reason}</p>
                    ) : null}
                    {doc.file_deleted_at ? (
                      <p className="text-muted-foreground text-xs">
                        File deleted under the retention rule on{" "}
                        {formatInZone(doc.file_deleted_at, zone)}.
                      </p>
                    ) : null}
                    {doc.has_file && canOpen ? (
                      <a
                        className={`${LINK} self-start text-sm`}
                        href={`${dealsPath(slug, id)}/documents/${doc.id}/file`}
                        target="_blank"
                        rel="noopener"
                      >
                        Open {doc.filename ?? "file"}
                        <span className="sr-only"> ({doc.label}, opens in a new tab)</span>
                      </a>
                    ) : null}
                  </div>
                  <div className="flex shrink-0 flex-col gap-2">
                    {canWrite && !closed && doc.state !== "verified" ? (
                      <UploadDocument
                        slug={slug}
                        dealId={id}
                        documentId={doc.id}
                        label={doc.label}
                        replace={doc.has_file}
                      />
                    ) : null}
                    {canOpen && doc.state === "received" ? (
                      <CheckDocumentForm
                        slug={slug}
                        dealId={id}
                        documentId={doc.id}
                        label={doc.label}
                      />
                    ) : null}
                  </div>
                </li>
              ))}
            </ul>
            {canWrite && !closed ? (
              <div className="mt-5 border-t pt-5">
                <AddDocumentForm slug={slug} dealId={id} />
              </div>
            ) : null}
          </Panel>

          <Panel title="History">
            <ol className="flex flex-col gap-3 text-sm" aria-label="Deal history">
              {deal.events.map((event) => (
                <li key={event.id} className="flex flex-wrap justify-between gap-2">
                  <span>
                    {eventLabel(event)}
                    {typeof event.details.reason === "string" ? (
                      <span className="text-muted-foreground"> · {event.details.reason}</span>
                    ) : null}
                  </span>
                  <time className="text-muted-foreground text-xs" dateTime={event.occurred_at}>
                    {formatInZone(event.occurred_at, zone)}
                  </time>
                </li>
              ))}
            </ol>
          </Panel>
        </div>

        <div className="flex flex-col gap-6">
          {canWrite && nextStages(deal).length > 0 ? (
            <Panel title="Stage" as="h3" divided={false}>
              <StageForm
                slug={slug}
                dealId={id}
                stages={nextStages(deal)}
                canOverride={workspace.role === "owner" && incomplete}
              />
            </Panel>
          ) : null}
          <Panel title="Details" as="h3" divided={false}>
            <DetailList
              className="sm:grid-cols-1"
              items={[
                {
                  label: "Customer",
                  value: (
                    <Link className={LINK} href={crmPath(slug, "contacts", deal.contact.id)}>
                      {deal.contact.label}
                    </Link>
                  ),
                },
                ...(deal.vehicle
                  ? [
                      {
                        label: "Car",
                        value: (
                          <Link
                            className={LINK}
                            href={automotivePath(slug, "vehicles", deal.vehicle.id)}
                          >
                            {deal.vehicle.label}
                          </Link>
                        ),
                      },
                    ]
                  : []),
                { label: "Agreed price", value: euros(deal.price_cents) },
                {
                  label: "Deposit",
                  value:
                    deal.deposit_cents !== null && deal.deposit_method
                      ? `${euros(deal.deposit_cents)} · ${DEPOSIT_METHOD_LABEL[deal.deposit_method]} · ${deal.deposit_received_on}`
                      : "Not recorded",
                },
                ...(deal.quote
                  ? [
                      {
                        label: "Quote",
                        value: (
                          <Link
                            className={LINK}
                            href={quotationsPath(slug, "quotes", deal.quote.id)}
                          >
                            {deal.quote.label}
                          </Link>
                        ),
                      },
                    ]
                  : []),
                ...(deal.conversation_id
                  ? [
                      {
                        label: "Conversation",
                        value: (
                          <Link
                            className={LINK}
                            href={inboxPath(slug, "conversations", deal.conversation_id)}
                          >
                            Open conversation
                          </Link>
                        ),
                      },
                    ]
                  : []),
                { label: "Created", value: formatInZone(deal.created_at, zone) },
              ]}
            />
          </Panel>
          {canWrite && open && deal.deposit_cents === null ? (
            <Panel title="Deposit" as="h3" divided={false}>
              <DepositForm slug={slug} dealId={id} />
            </Panel>
          ) : null}
          {canWrite && open ? (
            <Panel title="Sale options" as="h3" divided={false}>
              <SaleOptionsForm
                slug={slug}
                dealId={id}
                financed={deal.financed}
                hasTradeIn={deal.has_trade_in}
              />
            </Panel>
          ) : null}
        </div>
      </div>
    </>
  );
}
