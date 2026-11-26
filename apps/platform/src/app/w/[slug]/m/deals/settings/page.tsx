import { notFound } from "next/navigation";

import { withApi } from "@/lib/api-client";
import { getWorkspace } from "@/lib/data";
import { dealsPath } from "@/lib/deals";
import { requireOk } from "@/lib/guards";

import { FinanceSettingsForm, FormUpload } from "../_components/finance-forms";
import { ReviewSettingsForm } from "../_components/reviews";
import { DealSettingsForm } from "./settings-form";

type Props = { params: Promise<{ slug: string }> };

export default async function DealSettingsPage({ params }: Props) {
  const { slug } = await params;
  const path = dealsPath(slug, "settings");
  const workspace = requireOk(await getWorkspace(slug), path);
  if (!workspace.permissions.includes("deals.manage")) notFound();
  const settings = requireOk(
    await withApi((api) => api.GET("/v1/w/{slug}/deals/settings", { params: { path: { slug } } })),
    path,
  );
  const finance = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/finance/settings", { params: { path: { slug } } }),
    ),
    path,
  );
  const reviews = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/deals/reviews/settings", { params: { path: { slug } } }),
    ),
    path,
  );
  const channels = await withApi((api) =>
    api.GET("/v1/w/{slug}/inbox/channels", { params: { path: { slug } } }),
  );
  const whatsapp = channels.ok ? channels.data.items.filter((c) => c.kind === "whatsapp") : [];
  const templates = (
    await Promise.all(
      whatsapp.map(async (channel) => {
        const list = await withApi((api) =>
          api.GET("/v1/w/{slug}/inbox/channels/{channel_id}/whatsapp-templates", {
            params: { path: { slug, channel_id: channel.id } },
          }),
        );
        return list.ok
          ? list.data.items
              .filter((t) => t.usable)
              .map((t) => ({
                id: t.id,
                label: `${t.name} (${t.language}) · ${channel.name}`,
                paramCount: t.param_count,
                body: t.body,
              }))
          : [];
      }),
    )
  ).flat();
  return (
    <div className="flex flex-col gap-6">
      <section
        aria-labelledby="deal-settings-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="deal-settings-heading" className="text-base font-medium tracking-tight">
          Document checklist
        </h2>
        <p className="text-muted-foreground text-sm">
          New deals start with these documents. “Only when” adds an item only to financed deals,
          deals with a trade-in, or once a deposit is recorded. Existing deals keep their list.
        </p>
        <DealSettingsForm slug={slug} settings={settings} />
      </section>
      <section
        aria-labelledby="finance-settings-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="finance-settings-heading" className="text-base font-medium tracking-tight">
          Finance
        </h2>
        <p className="text-muted-foreground text-sm">
          The figures behind every finance estimate (the same simple-interest calculation as your
          website), and the forms customers fill in.
        </p>
        <FinanceSettingsForm slug={slug} settings={finance} />
        <div className="flex flex-col gap-2">
          <FormUpload
            slug={slug}
            kind="kyc"
            label="KYC & Loan Request Form"
            uploaded={finance.kyc_form}
            downloadHref={dealsPath(slug, "finance", "forms", "kyc")}
          />
          <FormUpload
            slug={slug}
            kind="ccr"
            label="CCR Form"
            uploaded={finance.ccr_form}
            downloadHref={dealsPath(slug, "finance", "forms", "ccr")}
          />
        </div>
      </section>
      <section
        aria-labelledby="review-settings-heading"
        className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
      >
        <h2 id="review-settings-heading" className="text-base font-medium tracking-tight">
          Google review requests
        </h2>
        <p className="text-muted-foreground text-sm">
          A few days after each car is collected, the customer is added to the Reviews list for
          staff to send. Nothing is sent automatically, and each sale gets one request at most.
        </p>
        <ReviewSettingsForm slug={slug} settings={reviews} templates={templates} />
      </section>
    </div>
  );
}
