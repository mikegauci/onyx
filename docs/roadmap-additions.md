# Roadmap additions

This file lists work the owner approved **outside** the 28 numbered PRs in `PR_ROADMAP.md`. That file is the planning kit and is kept verbatim. Items here follow the same rules as the roadmap (`CLAUDE.md`, `CLAUDE_WORKFLOW.md`): one item at a time, plan before edits, executable evidence, a draft PR, and no merge or deploy without the owner's approval.

| ID       | Phase      | Title                                        | Depends on                    | Effort | Status                                                                |
| -------- | ---------- | -------------------------------------------- | ----------------------------- | ------ | --------------------------------------------------------------------- |
| DF-001   | Foundation | Design foundation: research, tokens, base UI | PR-001                        | 6–10h  | Draft PR [mikegauci/onyx#2](https://github.com/mikegauci/onyx/pull/2) |
| SITE-001 | Marketing  | Build the Onyx Studio landing page (onyx.mt) | DF-001 (and PR-002 to deploy) | 20–32h | Approved 2026-11-04, not started                                      |

### DF-001 — Design foundation

- **Approved:** 2026-11-04, to land before PR-007.
- **Scope:** `docs/design/ui-references.md`, design tokens in `packages/ui/src/styles/globals.css`, a WCAG contrast test, base shadcn components, Geist fonts, dark default for the site. No product features or dashboard routes.

### SITE-001 — Build the Onyx Studio landing page

- **Approved:** 2026-11-04 by the owner, as a new item outside the 28-PR roadmap.
- **Depends on:** DF-001 merged (tokens and components). Deploying to a non-production URL needs PR-002. Live DNS for onyx.mt needs separate approval.
- **Estimated implementation:** 20–32h (rough order of magnitude, excludes waiting for copy, logos or legal text).
- **Implementation:** a single page in `apps/site`, following the direction in `docs/design/ui-references.md` §1:
  - glass nav;
  - hero with animated headline and product mock of the approval queue;
  - "how it works" flow (Enquiry → AI draft → Staff approval → Order → Fulfilment) with an animated beam;
  - module bento grid;
  - trust strip and pilot quote;
  - pricing cards (display only; values from config, not hard-coded logic);
  - CTA band;
  - footer with company and legal/privacy links.

  Use Motion and selected Magic UI components (MIT, copied in via the shadcn CLI), site only; no WebGL in v1. Metadata, Open Graph image and sitemap/robots.

- **Content:** the owner supplies or approves all copy, pricing, the pilot quote and any customer logos. Use placeholders clearly marked as such until then. No fake testimonials or logos.
- **Acceptance:**
  - Lighthouse (mobile) Performance ≥ 90, Accessibility ≥ 95, Best Practices ≥ 95, SEO ≥ 95 on a production build.
  - All animations stop under `prefers-reduced-motion`; content stays readable with JS disabled.
  - Keyboard navigation and visible focus work throughout; no horizontal scroll at 360px.
  - Vitest smoke tests for sections; a Playwright smoke test that loads the page and checks CTAs link to the platform URL.
  - `make check`, `make test`, `pnpm build` pass.
- **Non-goals:** CMS, blog, multi-language, contact form that stores data (needs a GDPR/privacy decision first), analytics/cookies (needs a consent decision), live DNS changes.
- **PR checklist:** tests; accessibility evidence; screenshots (desktop and mobile, with motion and with reduced motion); documentation; human review.
