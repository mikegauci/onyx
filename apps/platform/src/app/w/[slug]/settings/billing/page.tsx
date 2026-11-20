import { Badge } from "@onyx/ui/components/badge";
import {
  Table,
  TableBody,
  TableCaption,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@onyx/ui/components/table";

import { withApi } from "@/lib/api-client";
import { billingStatus, MONTH_PATTERN, recentMonths, usd } from "@/lib/billing";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { moduleLabel } from "@/lib/modules";
import { workspaceWith } from "@/lib/settings-guard";

import { ChoosePlan, ManageBilling } from "./billing-buttons";

type Props = {
  params: Promise<{ slug: string }>;
  searchParams: Promise<{ checkout?: string; month?: string }>;
};

export default async function BillingSettingsPage({ params, searchParams }: Props) {
  const { slug } = await params;
  const { checkout, month: rawMonth } = await searchParams;
  const path = `/w/${slug}/settings/billing`;
  const workspace = await workspaceWith(slug, "billing.read", path);
  const month = rawMonth && MONTH_PATTERN.test(rawMonth) ? rawMonth : undefined;
  const [billingResult, usageResult] = await Promise.all([
    withApi((api) => api.GET("/v1/w/{slug}/billing", { params: { path: { slug } } })),
    withApi((api) =>
      api.GET("/v1/w/{slug}/billing/usage", { params: { path: { slug }, query: { month } } }),
    ),
  ]);
  const billing = requireOk(billingResult, path);
  const usage = requireOk(usageResult, path);
  const canManage = workspace.permissions.includes("billing.manage");
  const status = billingStatus(billing.status);
  const months = recentMonths(new Date());
  const shown = month ?? months[0]!;
  const csv = `${path}/usage.csv?month=${shown}`;

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="billing-heading" className="flex flex-col gap-4">
        <h2 id="billing-heading" className="text-lg font-medium">
          Billing
        </h2>
        {checkout === "done" ? (
          <p role="status" className="rounded-md border p-3 text-sm">
            Thank you. Your plan updates here as soon as the payment is confirmed.
          </p>
        ) : checkout === "cancelled" ? (
          <p role="status" className="rounded-md border p-3 text-sm">
            Checkout cancelled. Nothing was charged.
          </p>
        ) : null}
        {!billing.configured ? (
          <p className="text-sm">
            Billing is not set up yet. Onyx support will contact you about your plan.
          </p>
        ) : null}
        <div className="flex flex-wrap items-center gap-3 text-sm">
          <span className="font-medium">
            {billing.plans.find((p) => p.key === billing.plan)?.name ?? "No plan"}
          </span>
          <Badge variant={status.variant}>{status.label}</Badge>
          {billing.current_period_end ? (
            <span className="text-muted-foreground">
              {billing.cancel_at_period_end ? "Ends" : "Renews"}{" "}
              <time dateTime={billing.current_period_end}>
                {formatInZone(billing.current_period_end, workspace.timezone)}
              </time>
            </span>
          ) : null}
        </div>
        {canManage && billing.has_customer ? <ManageBilling slug={slug} /> : null}
        {!canManage ? (
          <p className="text-muted-foreground text-sm">Only an owner can change the plan.</p>
        ) : null}
      </section>

      <section aria-labelledby="plans-heading" className="flex flex-col gap-4">
        <h2 id="plans-heading" className="text-lg font-medium">
          Plans
        </h2>
        <ul className="grid gap-4 sm:grid-cols-2" aria-label="Plans">
          {billing.plans.map((plan) => (
            <li key={plan.key} className="flex flex-col gap-3 rounded-md border p-4">
              <h3 className="font-medium">{plan.name}</h3>
              <p className="text-sm">{plan.modules.map(moduleLabel).join(", ")}</p>
              <p className="text-muted-foreground text-sm">
                AI included: {usd(plan.ai_monthly_usd * 1_000_000)} a month
              </p>
              {canManage && plan.available ? (
                <ChoosePlan
                  slug={slug}
                  plan={plan.key}
                  name={plan.name}
                  current={billing.plan === plan.key && billing.status !== "canceled"}
                />
              ) : null}
            </li>
          ))}
        </ul>
        <p className="text-muted-foreground text-xs">
          Changing plan switches modules on or off to match it. Without a plan, CRM and the inbox
          stay available.
        </p>
      </section>

      <section aria-labelledby="usage-heading" className="flex flex-col gap-4">
        <h2 id="usage-heading" className="text-lg font-medium">
          AI usage
        </h2>
        <form className="flex flex-wrap items-end gap-3" action={path}>
          <label className="flex flex-col gap-1 text-sm">
            Month
            <select
              name="month"
              defaultValue={shown}
              className="border-input bg-background h-9 rounded-md border px-3 text-sm"
            >
              {months.map((m) => (
                <option key={m} value={m}>
                  {m}
                </option>
              ))}
            </select>
          </label>
          <button type="submit" className="h-9 rounded-md border px-3 text-sm">
            Show
          </button>
          <a className="text-sm underline" href={csv} download>
            Download CSV
          </a>
        </form>
        <p className="text-sm">
          {usage.total_calls} calls, {usd(usage.total_cost_usd_micros)} of{" "}
          {usage.monthly_limit_usd_micros === null || usage.monthly_limit_usd_micros === undefined
            ? "no budget"
            : usd(usage.monthly_limit_usd_micros)}
        </p>
        {usage.lines.length === 0 ? (
          <p className="text-muted-foreground text-sm">No AI calls this month.</p>
        ) : (
          <Table>
            <TableCaption className="sr-only">AI usage by day</TableCaption>
            <TableHeader>
              <TableRow>
                <TableHead>Day</TableHead>
                <TableHead>Used for</TableHead>
                <TableHead className="text-right">Calls</TableHead>
                <TableHead className="text-right">Tokens in / out</TableHead>
                <TableHead className="text-right">Cost</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {usage.lines.map((line) => (
                <TableRow key={`${line.day}-${line.workload}`}>
                  <TableCell>{line.day}</TableCell>
                  <TableCell>{line.workload}</TableCell>
                  <TableCell className="text-right tabular-nums">{line.calls}</TableCell>
                  <TableCell className="text-right tabular-nums">
                    {line.input_tokens} / {line.output_tokens}
                  </TableCell>
                  <TableCell className="text-right tabular-nums">
                    {usd(line.cost_usd_micros, 6)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </section>
    </div>
  );
}
