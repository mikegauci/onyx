# Onyx Platform — Product Brief

## Agreed identity and domains

- **Onyx Studio** is the business, public brand and services website at **https://onyx.mt**.
- **Onyx Platform** is the multi-tenant SaaS product at **https://app.onyx.mt**.
- GitHub repository name: **onyx**. Keep one shared platform codebase.
- Development uses the coding assistant and model selected by the user. Shared instructions live in `AGENTS.md`; `CLAUDE.md` imports them for Claude Code. These documents do not select a model.
- Production AI remains provider-neutral (OpenAI and Anthropic); the coding model does not determine customer-facing models.
- Domain assignments are agreed deployment targets, not confirmation that DNS or hosting has been configured.

**Status:** Recovered and updated Claude Code / Opus 5.5 planning baseline, 4 November 2026 (original plan: 27 October 2026)  
**Product:** Onyx Platform, a reusable multi-tenant AI operations SaaS delivered by Onyx Studio.  
**First tenant:** Malta-based lighting retailer.  
**Future tenants:** Retail, catering, hospitality, construction and service businesses.

## Implementation ownership and AI model policy

- **Engineering environment:** the coding assistant/model selected by the user; Claude Code and Codex use the same repository rules. The development assistant does not determine runtime models for customer conversations.
- **Project memory and guardrails:** root [`AGENTS.md`](AGENTS.md), imported by [`CLAUDE.md`](CLAUDE.md); task details in [`PR_ROADMAP.md`](PR_ROADMAP.md). Follow [`CLAUDE_WORKFLOW.md`](CLAUDE_WORKFLOW.md) when opening/reviewing PRs.
- **Runtime LLM policy:** a provider adapter supporting Anthropic and OpenAI, with models selected per tenant/workload based on evaluations, latency, privacy and cost. Do not hardcode Opus 5.5 into customer-facing features just because it builds the software.
- **Work sequencing:** one numbered, reviewable PR at a time. Complete and verify the acceptance criteria before starting the next PR. A human reviews before merge and production changes.

## Vision

Build one production SaaS with independently enabled business modules and tenant-specific extensions. Do not clone the application per client. Focus on measurable operational improvements, not autonomous AI for its own sake.

## Business goals

1. Reduce response time for inbound enquiries and missed leads.
2. Streamline product discovery and quotations without fabricating prices, stock or policies.
3. Connect accepted quotes to reliable order and fulfilment workflows.
4. Reuse the same platform for subsequent clients; onboard via settings, integrations and modules.
5. Monetise with implementation fees, SaaS subscriptions and metered AI/integration usage.

## First tenant / first release

A single customer journey must work: inbound enquiry → contact/lead → product lookup → **draft** quotation → staff approval → outbound response → accepted quote → order → inventory check/reservation → fulfilment task → customer notification.

### MVP deliverables

- Secure login and organisation-based multi-tenancy with verified isolation.
- Tenant workspace, users and role-based access.
- Module registry with backend entitlement enforcement.
- Leads/customers, product catalogue (import or sync), inventory view, quotations.
- Unified conversation record, email integration; WhatsApp follows when external onboarding is available.
- AI assistant with tool calling, read-only catalogue search, safe quotation drafts and human review.
- Per-tenant AI consumption logging, spend ceilings and traceable tool executions.
- Basic audit logs, metrics, monitoring and production runbook.

### Full first-client release

- Temporal workflows for customer follow-up, approvals, orders and fulfilment.
- Duplicate-event protection, retry and reconciliation handling.
- Integration adapters for at least one actual inventory/POS data source.
- Operator tools for failed workflows, exceptions and manual overrides.
- SaaS tenant provisioning, usage billing and a second-industry reuse proof.

## Explicit non-goals for initial release

- Full ERP or accounting replacement; complex payroll.
- Arbitrary no-code workflow builder.
- Autonomous AI refunds, purchasing or payments.
- Complex multi-agent coordination before simple agents are validated.
- Native mobile applications.
- An application deployment or database per tenant by default.
- Kubernetes / GPU model hosting / training a foundational LLM.

## Architecture decisions

| Area | Choice | Notes |
|---|---|---|
| Web | Next.js, React, TypeScript, Tailwind, shadcn/ui on Vercel | Public site at onyx.mt; dashboard at app.onyx.mt |
| API | Python, FastAPI, Pydantic | Domain-oriented modular monolith |
| Database | Supabase managed PostgreSQL | Auth + Storage + pgvector; tenant-scoped records |
| Persistence | SQLAlchemy 2 + Alembic | **One migration authority:** Alembic, including SQL for RLS |
| Authentication | Supabase Auth | FastAPI verifies JWT and resolves tenant membership server-side |
| Tenant security | PostgreSQL RLS + API authorisation | Test cross-tenant isolation at both layers |
| Automation | Temporal Cloud + Python workers on Render | Start locally; production workers run continuously |
| AI | Pydantic AI with provider abstraction for OpenAI/Anthropic | Typed outputs/tools; LangGraph only if complex stateful graphs justify it |
| Retrieval | PostgreSQL full-text + pgvector | Tenant filters required throughout |
| Integration | Provider adapters, webhooks and outbox/event table | Signed webhooks, idempotency, retries |
| Payments | Stripe Billing | SaaS billing, not a replacement for client order payments |
| Observability | OpenTelemetry + Pydantic Logfire + Sentry + structured logs | Avoid exposing secrets or unnecessary PII |
| Hosting | Vercel + Render + Supabase + Temporal Cloud | Staging/prod separation |

## Deployment baseline

Use appropriate EU regions for Vercel, Render, Supabase and Temporal where supported by the selected services; verify actual availability, subprocessors and data-processing terms before production. Region selection alone does not establish EU-only data residency. Use GitHub Actions and Docker, Render Blueprints for API/worker services, and Terraform only where justified. Generate the TypeScript API client from FastAPI OpenAPI. Pin supported dependency versions during implementation rather than assuming the planning date defines versions.

## Design constraints for multi-industry reuse

- Use a **single modular monolith** with tenant-specific configuration, not repository forks or copied apps for each customer.
- Shared foundations: CRM, quotations, inbox, auth, audit, integrations, AI gateway and workflow execution. Industry extensions are additive and bounded; retail, catering, construction and hospitality must not require changing the core's assumptions.
- Modules own domain-level types, API contracts, migrations, policy checks and UI. Disabling a module must disable server-side capabilities as well as navigation.
- External systems remain authoritative for their own data unless the integration contract explicitly defines otherwise. All synchronisation has mapping, idempotency and reconciliation paths.
- Start with a **supervised** pilot to validate value; don't imply the whole 28-PR platform fits within a small client pilot budget.

## Essential security and reliability rules

- `organization_id` must be derived from the authenticated workspace and checked against membership, **never** trusted merely because the request supplies an ID.
- PostgreSQL tenant-owned tables must have RLS enabled, with privileges and policies tested against real app roles. Service-role bypass is prohibited in ordinary tenant request paths.
- Use transaction-scoped tenant context where the database connection role and RLS policy design require it; connection pooling and worker jobs must never leak context between tenants.
- AI tools get narrow permissions and typed inputs. The LLM does not directly execute SQL, set prices, issue refunds, send purchase orders or modify stock without application controls.
- Financial/order actions require deterministic domain services, auditable approvals, and idempotency keys.
- External webhooks must be authenticated and deduplicated.
- Encrypt integration credentials; keep keys only in server-side secret stores.
- Provide retention, export/deletion, client data-processing terms and EU/GDPR review before go-live.
- Establish backup/restore procedures, alerting and incident response for production.

## Release criteria

### Pilot

- The shop can import/verify products; staff can see and approve draft quotes.
- The AI answers against verified catalogue/policy data and **does not invent** stock, prices or lead times.
- Every customer-facing AI reply can be held for review; human handoff works.
- Two separate test tenants cannot access or retrieve one another's information by API, SQL or RAG.
- Tested cost/usage limits and an operational fallback to manual customer support.

### First production customer

- A quote-to-order-to-fulfilment workflow survives worker restarts and repeated webhooks without double-processing.
- Defined monitoring, incident ownership, secrets rotation and backup restore verification.
- Client acceptance sign-off against an agreed process map and KPIs.
- Simple documentation and staff training delivered.

## Suggested KPIs

Baseline before build, then weekly measurement: median enquiry response time; enquiries resolved without staff intervention; quote preparation minutes; quote acceptance rate; duplicate/reconciliation errors; human escalation rate; AI cost per completed enquiry; order-processing time; monthly active staff users.

## Effort and calendar estimate

The full 28-PR product is **larger** than a one-off lighting-shop integration. Summed PR estimates are roughly **587–1,019 engineering hours** (including platform commercialisation and second-industry proof). At 35 productive engineering hours/week this is approximately **17–30 engineering weeks**, before vendor approvals and client delays.

- **Small commercial validation pilot:** 2–4 weeks if built as a narrowly scoped integration **outside** the complete SaaS foundation; avoid implying that the full reusable platform can be delivered in that time.
- **First reusable-platform supervised pilot, through PR-018:** approximately 354–593 hours, or **10–17 engineering weeks**, reducible by deferring optional RAG and noncritical UI refinements.
- **First-client complete order and fulfilment operations, through PR-024:** approximately 489–839 hours, or **14–24 engineering weeks**; allow further calendar time for API access, Meta approvals and customer UAT.
- **Commercial platform plus second-industry proof, through PR-028:** approximately 587–1,019 hours, or **17–30 engineering weeks**; rollout and approvals may push calendar duration longer.
- **Reuse for a similar second client:** often 2–6 weeks of incremental onboarding and configuration after the platform exists; a new vertical may need substantial extension work.

These are order-of-magnitude planning ranges, not delivery guarantees. Use narrow scope and milestone acceptance criteria to control cost.
