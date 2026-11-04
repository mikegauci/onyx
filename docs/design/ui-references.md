# UI references and design direction

Status: **draft for owner review** · Date: 2026-11-04 · Scope: Onyx Studio site (`apps/site`, onyx.mt) and Onyx Platform dashboard (`apps/platform`, app.onyx.mt).

## Method and limits

- The Mobbin connector was connected, but every search returned "requires a paid plan". These references therefore come from **public web pages** (Awwwards, product sites, product docs and help centres), not Mobbin. No entry has a Mobbin link.
- The owner asked for "modern, dark, cool animations". The landing-page section weights that heavily. The app section weights density, accessibility and trust, because staff will use it all day.
- **References are for patterns only.** Do not copy any product's logo, wordmark, illustrations, exact palette, copy or page layout. Every Onyx token below is our own choice.
- Observations of live sites were made on 2026-11-04 and may change.

---

## 1. Landing page (onyx.mt, Onyx Studio)

### Overall mood: dark, near-black canvas with restrained motion

| Source                                                        | Link                                                                                                           | What to borrow                                                                                                                                        | Why                                                                                                                                         |
| ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Resend homepage                                               | https://resend.com/                                                                                            | Near-black canvas. A large display headline that fades/blurs in on load. One soft diagonal "light beam" gradient behind the hero. Very little colour. | Shows that a dark page feels premium through light and type rather than many colours. Cheap to build with CSS gradients.                    |
| Raycast homepage                                              | https://www.raycast.com/                                                                                       | Floating, translucent, blurred nav bar (glass pill) over a dark page. Hero text reveals from low opacity.                                             | A glass nav is a recognisable "modern SaaS" cue and fits shadcn `NavigationMenu`.                                                           |
| Linear homepage                                               | https://linear.app/                                                                                            | Dark neutral (not pure black) background. Thin 1px hairline borders. Sections fade in on scroll. Product UI shown as the hero visual.                 | Using the real product as the hero builds trust better than abstract art, and suits Onyx because the approval queue _is_ the selling point. |
| Oryzo AI, Awwwards Site of the Day (13 Apr 2026, by Lusion)   | https://www.awwwards.com/sites/oryzo-ai                                                                        | Very dark warm-black (`#100904`-ish) with one hot orange accent. Awwwards tags: 3D, transitions, filters and effects.                                 | Evidence that a **single warm accent on near-black** is award-level, and distinct from the indigo/violet most AI SaaS sites use.            |
| Heron AI, Awwwards Site of the Day (12 Oct 2026, by Bearplus) | https://www.awwwards.com/sites/heron-ai                                                                        | Scroll-driven storytelling with line drawings and one orange scan-line. Awwwards tags: animation, scrolling, storytelling.                            | The "scan line" idea suits a "how it works" story (an enquiry being read and turned into a quote).                                          |
| Awwwards SaaS gallery                                         | https://www.awwwards.com/websites/saas/ · Sites of the Day https://www.awwwards.com/websites/sites_of_the_day/ | Ongoing inspiration feed.                                                                                                                             | Use it to check direction before landing-page work, not as a template source.                                                               |

### Section patterns

| Section                   | Pattern to use                                                                                                                                                                                                                                | Reference                                                                                                                                                     | Notes for Onyx                                                                                                                              |
| ------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| **Hero**                  | Headline + one-line value prop + two CTAs ("Book a demo", "See how it works"). Below it, a framed dark screenshot or animated mock of the approval queue, with a soft radial glow behind it.                                                  | Linear, Resend                                                                                                                                                | The headline animates in once with blur and opacity over about 600ms, then stays still. No auto-playing video.                              |
| **How it works**          | 4–5 steps in a horizontal flow (Enquiry → AI draft → Staff approval → Order → Fulfilment) joined by an **animated beam** line that travels between nodes as the section scrolls into view.                                                    | Heron AI (scan-line storytelling); Magic UI `animated-beam` (https://magicui.design/docs/components/animated-beam)                                            | Tells the human-approval story visually. Shows "AI drafts, humans decide" without long copy.                                                |
| **Feature / module grid** | Bento grid of 5–7 cards (CRM, Inbox, Catalogue & stock, Quotes, Approvals, AI assistant, Usage). Each card has a tiny live-looking UI fragment. On hover, the border gets a moving highlight ("border beam") or a cursor-following spotlight. | Magic UI `border-beam` / `magic-card` (https://magicui.design/docs/components/border-beam); Aceternity UI card effects (https://ui.aceternity.com/components) | A bento grid maps cleanly onto "enableable modules" (each card is one module) and can later reflect real entitlements.                      |
| **Social proof / trust**  | Logo marquee (pauses on hover, stops for reduced motion). One pull-quote card from the pilot. A trust strip: "EU data residency", "Human approval on every quote", "Per-tenant isolation".                                                    | Magic UI `marquee` (https://magicui.design/docs/components/marquee)                                                                                           | We don't have customer logos yet. Start with the trust strip and a single pilot quote, and use real logos only with the owner's permission. |
| **Pricing**               | 3 plan cards. The middle one is highlighted with an accent border and glow. Monthly/annual toggle. Comparison table below. "Talk to us" for the custom tier.                                                                                  | Resend pricing (https://resend.com/pricing), Linear pricing (https://linear.app/pricing)                                                                      | Pricing values come from Stripe/backend later. The site only shows them.                                                                    |
| **CTA**                   | Full-width dark band with a grid or dot texture, a radial accent glow, a short headline and one button.                                                                                                                                       | Resend, Raycast                                                                                                                                               | Reuse the hero glow token so the page starts and ends the same way.                                                                         |
| **Footer**                | 4-column link grid, a small wordmark, status/legal links, and a big muted wordmark watermark at the bottom.                                                                                                                                   | Linear, Resend                                                                                                                                                | Include the Malta company details and privacy/GDPR links, which are needed before live data (see `CLAUDE.md`).                              |

### Animation toolkit (site only)

- **Motion** (motion.dev, formerly Framer Motion) for entrance and scroll-linked animations.
- **Magic UI** components (shadcn registry, MIT): `animated-beam`, `border-beam`, `marquee`, `blur-fade`, `number-ticker`. Installing them with the shadcn CLI copies the source into the repo, so we own and theme it.
- **Aceternity UI** only for one-off hero effects. Check the licence first: free and Pro tiers differ (https://ui.aceternity.com).
- **Avoid WebGL/3D for v1.** The Awwwards references use it, but it hurts LCP and accessibility and costs more to maintain. Get the same "cool" feel with CSS gradients, blur and SVG beams. Revisit WebGL once the site has content.
- Every animation must respect `prefers-reduced-motion`: show content immediately with no movement.

---

## 2. App (app.onyx.mt, Onyx Platform dashboard)

### Patterns

| Pattern                               | Reference                                                                                                                                                                                                                                                                      | What to borrow                                                                                                                                                                                                                                                                                | Why                                                                                                                                                                |
| ------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Sidebar and workspace switcher**    | Linear (https://linear.app/docs/triage, UI refresh https://linear.app/changelog/2026-03-12-ui-refresh); shadcn `sidebar` block (https://ui.shadcn.com/blocks)                                                                                                                  | Collapsible left sidebar. Workspace switcher at the top (avatar, name, chevron, dropdown of memberships). Grouped nav by module. User menu at the bottom. `⌘K` command palette.                                                                                                               | Matches `/w/{slug}`: switching workspace changes the slug, and the server re-resolves membership. shadcn ships an accessible sidebar we can theme.                 |
| **Unified inbox / conversations**     | Linear Triage inbox (https://linear.app/docs/triage); Intercom inbox + Copilot (https://www.intercom.com/help/en/articles/9121374-copilot-explained)                                                                                                                           | Three panes: conversation list (unread dot, channel icon, assignee, SLA age) · thread · context panel (customer, lead, linked quote). Keyboard navigation (j/k, e to close).                                                                                                                  | This is the standard for support/sales inboxes. The context panel is where the lead and quote links live (PR-011, PR-009).                                         |
| **Lead / CRM tables**                 | Attio table views (https://attio.com/help/reference/managing-your-data/views/create-and-manage-table-views.md); record split view (https://attio.com/help/reference/attio-101/attios-data-model/understanding-records.md)                                                      | Dense table: sticky header, saved views (tabs), filter chips, sortable columns, bulk-select toolbar, row click opens a **side sheet**, and a full record page for deep work.                                                                                                                  | Saved views and filter chips scale to every vertical. TanStack Table + shadcn `data-table` gives this out of the box.                                              |
| **Product catalogue with stock**      | Attio tables (pattern); Linear list density                                                                                                                                                                                                                                    | Table with thumbnail, SKU in mono font, price (tabular numbers, right-aligned), stock badge (In stock / Low / Out with colour + icon + text), "last synced" timestamp per row.                                                                                                                | Stock status must not rely on colour alone (accessibility). "Last synced" makes stale data visible, as the AI-safety rules require.                                |
| **Quote builder**                     | Stripe quotes editor (https://docs.stripe.com/quotes/create)                                                                                                                                                                                                                   | Customer header · line-item table (product search combobox, qty, unit price, discount, VAT rule, line total) · totals panel on the right (subtotal, VAT by rate, total) · status pill (Draft / Pending approval / Sent / Accepted).                                                           | Totals are **computed by the backend and only displayed**. The UI shows a "recalculating…" skeleton and never calculates money itself (see `CLAUDE.md`).           |
| **Staff approval queue**              | Linear Triage (accept/decline/snooze); Strobes HITL queue (https://help.strobes.co/en/article/human-in-the-loop); HITL interface guidance (https://www.gravitee.io/corpus/gen-1980/human-computer-interaction/human-in-the-loop-approval-interfaces-for-ai-agent-actions.html) | Queue tabs with counts (Pending / Changes requested / Approved / Rejected) · age/SLA chip · item view showing the **exact draft** (email + quote) with a diff of staff edits · actions: **Approve & send**, **Edit**, **Request changes**, **Reject (reason required)** · keyboard shortcuts. | The reviewer approves the exact payload. If the payload changes after approval, it must be approved again. Rejection reasons feed back into evals. Maps to PR-017. |
| **AI assistant panel with citations** | Intercom Copilot: answer plus source list, and the source opens in the sidebar with the used passage highlighted (https://www.intercom.com/help/en/articles/8587194-how-to-use-copilot)                                                                                        | Right-side drawer. Answer with numbered inline citations `[1]`; clicking one opens the product/price/policy record with the passage highlighted. An explicit "No grounded answer — escalate" state. A confidence/"needs review" badge.                                                        | Our retrieval must be grounded and able to abstain, so the UI needs a first-class abstain state, not just a happy path.                                            |
| **Usage / AI budget meters**          | Vercel usage dashboard and spend management (https://vercel.com/docs/limits/usage)                                                                                                                                                                                             | Per-metric meter cards (used / limit, % bar, projected end-of-cycle), threshold markers at 50/80/100%, a spend-limit setting with a clear "what happens at the limit" explanation.                                                                                                            | Maps to per-tenant metering and budgets (PR-013). Meters use warning/destructive tokens and always show the number as text.                                        |
| **Settings**                          | shadcn settings layout; Linear settings                                                                                                                                                                                                                                        | Left sub-nav (General, Members & roles, Modules, Integrations, Billing, AI & budgets). Each section is a stack of cards. Dangerous actions sit in a separated "Danger zone" card.                                                                                                             | A predictable structure lets later PRs add sections without redesigning anything.                                                                                  |
| **Platform admin (`/admin`)**         | Same shell, visibly different                                                                                                                                                                                                                                                  | Same layout, but with a persistent **admin banner** and a different sidebar accent, so staff never confuse admin with a tenant workspace. Tenant table, impersonation is never silent and every action is audited.                                                                            | Prevents mistakes about which context you're in. Supports the audit requirement (PR-006, PR-025).                                                                  |
| **Empty / loading / error states**    | shadcn `skeleton`; Linear empty states                                                                                                                                                                                                                                         | Empty: icon + one sentence + primary action ("Import leads CSV"). Loading: skeletons that match the final layout (no spinners for tables). Error: inline alert with a retry and a support reference ID. Module disabled: explicit "not enabled for this workspace" state.                     | PR-007 acceptance needs loading/error states. A "disabled module" state supports PR-008 entitlements.                                                              |

### AI-specific UI conventions

- AI-generated content always carries an **"AI draft"** badge in the AI accent colour until a human approves it.
- A human-approved item shows who approved it and when, as an audit trail visible in the UI.
- Never animate AI output as a "typing" effect for money or quantities. Show the final validated value from the backend.

---

## 3. Recommended direction

### Character

A dark-first, near-black product with **one warm "ember" accent**. The ember suggests heat and light under black stone (onyx) and Malta's warm limestone, and stands apart from the indigo/violet most AI products use. The site is dramatic; the app is calm and dense.

### Colour tokens (OKLCH, shadcn variable names)

Neutrals have a slight warm tint (hue ≈ 60, chroma ≤ 0.01). `packages/ui/src/styles/globals.contrast.test.ts` checks every pair automatically (target ≥ 4.5:1 for text, ≥ 3:1 for UI borders and focus).

| Token                              | Light                                       | Dark                    | Use                                                          |
| ---------------------------------- | ------------------------------------------- | ----------------------- | ------------------------------------------------------------ |
| `--background`                     | `oklch(0.99 0.002 60)`                      | `oklch(0.145 0.004 60)` | Page                                                         |
| `--foreground`                     | `oklch(0.17 0.005 60)`                      | `oklch(0.96 0.004 60)`  | Body text                                                    |
| `--card` / `--popover`             | `oklch(1 0 0)`                              | `oklch(0.18 0.005 60)`  | Raised surfaces                                              |
| `--muted`                          | `oklch(0.965 0.003 60)`                     | `oklch(0.22 0.005 60)`  | Subtle fills                                                 |
| `--muted-foreground`               | `oklch(0.48 0.008 60)`                      | `oklch(0.70 0.008 60)`  | Secondary text                                               |
| `--border`                         | `oklch(0.91 0.004 60)`                      | `oklch(1 0 0 / 9%)`     | Decorative hairlines                                         |
| `--input`                          | `oklch(0.62 0.006 60)`                      | `oklch(0.48 0.006 60)`  | Form-control borders (≥ 3:1)                                 |
| `--primary`                        | `oklch(0.17 0.005 60)`                      | `oklch(0.96 0.004 60)`  | Primary buttons (ink-on-paper, inverted in dark)             |
| `--primary-foreground`             | `oklch(0.99 0.002 60)`                      | `oklch(0.17 0.005 60)`  |                                                              |
| `--brand` (new)                    | `oklch(0.55 0.17 42)`                       | `oklch(0.74 0.16 52)`   | Ember: links, focus ring, AI badges, highlights, hero glow   |
| `--brand-foreground` (new)         | `oklch(0.99 0 0)`                           | `oklch(0.17 0.005 60)`  | Text on ember                                                |
| `--ring`                           | = ember                                     | = ember                 | Focus                                                        |
| `--success` (+ `-foreground`, new) | `oklch(0.50 0.13 155)`                      | `oklch(0.72 0.15 155)`  | In stock, approved                                           |
| `--warning` (+ `-foreground`, new) | `oklch(0.52 0.12 70)`                       | `oklch(0.80 0.15 85)`   | Low stock, 80% budget                                        |
| `--destructive` (+ `-foreground`)  | `oklch(0.53 0.21 27)`                       | `oklch(0.68 0.19 25)`   | Reject, out of stock, errors; dark mode uses dark text on it |
| `--info` (+ `-foreground`, new)    | `oklch(0.50 0.13 240)`                      | `oklch(0.72 0.12 240)`  | Neutral notices                                              |
| `--chart-1..5`                     | ember, blue, teal, amber, slate             | lighter variants        | Usage charts                                                 |
| `--sidebar-*`                      | shadcn sidebar set, one step off background |                         | Shell                                                        |

Keep shadcn's own `--accent` (hover fill) neutral, and add `--brand` as a separate token (Tailwind utilities `bg-brand`, `text-brand`), so shadcn components keep working unchanged.

### Typography

- **Geist Sans** (UI and site) and **Geist Mono** (SKUs, IDs, code), via the `geist` npm package and `next/font`. Both are open-source (OFL).
- Site display headlines: Geist, weight 600, tracking −0.03em, sizes clamped 40–72px. Optionally pair with a serif for one emphasised word (e.g. Instrument Serif, OFL); owner's call.
- App: base 14px / line-height 20px; tables 13px; `font-variant-numeric: tabular-nums` on every number, price and quantity column.

### Spacing, radius, density

- Spacing: Tailwind's 4px scale. App page padding is 24px; site sections use 96–128px vertical rhythm.
- Radius: `--radius: 0.5rem` (sm 4px, md 6px, lg 8px, xl 12px). Slightly tighter than the shadcn default for a more "tool-like" feel.
- Density (app): control height 32px (sm) / 36px (default); table rows 36px compact / 44px comfortable; sidebar 240px expanded / 52px collapsed.
- Elevation: borders before shadows. In dark mode, show elevation with a lighter surface plus a 1px top highlight, not drop shadows.

### Motion tokens

- Durations: `--duration-fast: 120ms` (hover/press), `--duration-base: 200ms` (menus, sheets), `--duration-slow: 400ms` (site reveals).
- Easing: `--ease-onyx: cubic-bezier(0.2, 0, 0, 1)` (Tailwind utility `ease-onyx`).
- The app uses CSS transitions only. Motion and Magic UI are site-only, to keep the platform bundle light.
- A global `@media (prefers-reduced-motion: reduce)` rule turns off transforms and animations.

### Theme defaults

- Site: dark only for v1 (`class="dark"` on `<html>`).
- Platform: light until PR-007 adds system-preference detection and a user toggle. Both themes are first-class and tested.

### Key layout patterns (summary)

1. App shell: sidebar + workspace switcher + top bar (breadcrumb, `⌘K`, AI panel toggle).
2. List → side sheet → full page for every record type.
3. Three-pane inbox.
4. Builder page with sticky totals rail (quotes).
5. Review queue with tabs, item detail, sticky action bar (approvals).
6. Right-hand AI drawer with citations and an abstain state.
7. Card-stack settings with a danger zone.
8. Site: hero → beam "how it works" → module bento → trust → pricing → CTA → footer.

## Sources

- Awwwards: https://www.awwwards.com/websites/saas/ · https://www.awwwards.com/websites/sites_of_the_day/ · https://www.awwwards.com/sites/oryzo-ai · https://www.awwwards.com/sites/heron-ai
- Sites: https://resend.com/ · https://www.raycast.com/ · https://linear.app/
- Docs: https://linear.app/docs/triage · https://linear.app/changelog/2026-03-12-ui-refresh · https://attio.com/help/reference/managing-your-data/views/create-and-manage-table-views.md · https://www.intercom.com/help/en/articles/9121374-copilot-explained · https://www.intercom.com/help/en/articles/8587194-how-to-use-copilot · https://docs.stripe.com/quotes/create · https://vercel.com/docs/limits/usage · https://help.strobes.co/en/article/human-in-the-loop · https://www.gravitee.io/corpus/gen-1980/human-computer-interaction/human-in-the-loop-approval-interfaces-for-ai-agent-actions.html
- Component libraries: https://magicui.design · https://ui.aceternity.com · https://ui.shadcn.com/blocks
