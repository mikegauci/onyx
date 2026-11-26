# VA-013 — Rebuild ventur.com.mt on Onyx stock

Status: planned 2026-11-26. Approved by the owner on 2026-11-24 (it replaces the VA-012 audit).
Depends on VA-001 (vehicles in Onyx), which is merged.

The site is built in a **new repository, `ventur`**
(`/Users/michaelgauci/GitHub/ventur`, GitHub `mikegauci/ventur`, private). Onyx supplies the
stock, and is where Ventur adds and edits cars from now on (owner decision 2026-11-26). The
Onyx-side work (part 0) is built in the `onyx` repo; the site only reads Onyx's public stock
API and never reaches into Onyx in any other way.

## Goal

A fast, mobile-first site for Ventur Auto Import, a Malta car dealer (used and Japan-imported
cars, vans and trucks; in-house finance; "risk-free import"). Its stock comes live from Onyx, so
a car that is sold or reserved in Onyx changes on the site without anyone editing the site.

Acceptance (from the roadmap):

- Ventur adds and edits cars, photos and prices in Onyx, and WordPress is retired.
- Sold and reserved cars update on the site without manual edits (within 5 minutes).
- Stock search with filters, and a vehicle page with photos and specs.
- Enquiries reach Ventur (the Onyx inbox once allowed; see Enquiries).
- Lighthouse on mobile, on the production build, for the homepage, search and a vehicle page:
  - Performance ≥ 90;
  - Accessibility, Best Practices and SEO ≥ 95.
- SEO metadata, structured data, a sitemap from live stock, and redirects so no indexed URL of
  the old site returns 404.

## The current site (what we replace)

WordPress with the Vehica theme, Elementor and WooCommerce. From its sitemaps (2026-11-26):

- **About 850 car listings** at `/listing/{slug}/` (for example
  `/listing/toyota-dyna-euro-6-japan-import/`), and the search at `/search/`.
- **Make pages** at `/search/{make}/` (41 makes), plus pages for the other taxonomies
  (`vehica_6654`, `vehica_6655`, ... in the sitemap index).
- **13 pages:**
  - kept: `/`, `/about-us/`, `/our-team/`, `/faq/`, `/risk-free-import/`,
    `/loan-calculator/`, `/contact-us/`, `/sold/`;
  - dropped, each redirected: `/panel/`, `/login-register/`, `/compare/`, `/map-search/`,
    `/404-page/`.
- **2 blog posts:** `/14-surprisingly-affordable-luxury-cars/` and
  `/12-reasons-to-choose-ventur-auto-imports/`.

**Car photos are hosted on the WordPress site** (`/wp-content/uploads/...`). They must be copied
before WordPress is switched off, or every photo breaks (part 0a).

## Decisions

- **Stack:** Next.js 16 (App Router), React 19, TypeScript strict, Tailwind CSS 4, pnpm, Node 24.
  This matches Onyx's `apps/site`. It is hosted on Vercel.
  - **Owner decision:** Vercel's Hobby plan is for non-commercial use, so a client's live site
    should be on Pro or on the Onyx Studio team.
- **Same URLs where possible:**
  - Vehicle pages stay at `/listing/{slug}/` and make pages at `/search/{make}/`, so most links
    and search rankings carry over with no redirect.
  - A car imported from WordPress keeps its WordPress slug. A car added in Onyx gets a new
    slug, and a slug never changes once the car is listed.
- **Content for the non-stock pages:**
  - It lives in the repo as typed content files (TS or MDX); there is no CMS in v1.
  - The draft copy is taken from Ventur's own current pages and rewritten, and Ventur approves
    it.
  - A CMS can follow if Ventur wants to edit pages themselves.
- **Rendering:**
  - Stock pages are server-rendered with incremental static regeneration (revalidate every 5
    minutes), plus an on-demand revalidation hook Onyx can call when a car changes.
  - Onyx's API is on a free Render plan and sleeps when idle, so the site must never wait on it
    to render a cached page. If the API is unreachable, the last good page is served.
- **No VIN, no internal data:** the public stock shows what the old site showed (make, model,
  year, mileage, fuel, transmission, body, colour, engine size, doors, price, features, photos,
  video) and the status. Never the VIN, the deal, the customer, or `held_by_deal_id`.
- **Status on the site:**
  - `available`: shown.
  - `reserved`: shown with a "Reserved" badge, and no "buy" wording.
  - `sold`: off the search. Its page stays for 30 days, saying it is sold and showing similar
    cars, and it appears on `/sold/`. After 30 days it redirects to its make page.
  - `withdrawn`: its page redirects to its make page.

## Part 0 — Onyx side (in the `onyx` repo)

Owner decision (2026-11-26, option A): **Onyx becomes the one place where Ventur manages its
stock.** WordPress is imported once more at launch, then retired. Today Onyx can only import
cars from WordPress; it has no screen to add or edit a car. Part 0 adds that, plus the public
API the website reads.

It is built in the onyx repo with the normal Onyx flow (plan, branch, PR, preview migration,
production migration on approval), as three PRs. The `ventur` repo session does not build it.

### 0a — Stock management in Onyx (about 16–24h)

- **Add and edit a car** under Automotive → Vehicles:
  - the same fields the import fills: title, make, model, variant, year, mileage, engine size,
    fuel, transmission, body, colour, doors, condition, price (or "price on request"),
    features, video link and stock number;
  - the VIN, which stays internal.
- **Photos:**
  - upload several at once (JPEG, PNG, WebP, HEIC from phones), reorder them by dragging,
    choose the cover photo and delete;
  - Onyx stores the original and makes resized web versions (WebP, for example 400, 800 and
    1600 px wide);
  - size and type limits, and an image check (a file must really be an image);
  - photos sit in a public bucket, because they appear on the public website.
- **Status:** available, reserved, sold or withdrawn, changed by staff.
  - A car held by an open deal keeps the status the deal gives it, as today (VA-007).
  - Every change is audited and written as a vehicle event, so the daily summary (VA-010)
    keeps counting listings.
- **Where each car came from:** a new `origin` (`import` or `manual`).
  - The WordPress import only updates or withdraws cars it imported. A car added in Onyx is
    never withdrawn because it is missing from WordPress.
  - A switch turns the WordPress source off at launch, so nothing is imported after that.
- **One-off photo copy:** copy each current car's photos from WordPress into Onyx storage, so
  they keep working after WordPress is switched off.
  - "Current" means available and reserved cars, and cars sold in the last 30 days. Most of
    the ~850 WordPress listings are old sold cars, and copying all of them would not fit the
    free storage plan.
- **Permissions:** owners and admins manage stock (a new `vehicles.manage` permission), and
  members can read it. This is checked in the API.
- Tests:
  - creating, editing and changing the status of a car, with every change audited;
  - photo upload limits, ordering and the cover photo;
  - a car added in Onyx surviving an import;
  - a held car keeping its status;
  - a two-tenant negative test on every endpoint.

### 0b — Public stock API for the website (about 8–14h)

- Migration:
  - `automotive_vehicles.slug`: unique per tenant. It is filled from the last part of each
    vehicle's WordPress `listing_url`, and generated from make, model and year for cars added
    in Onyx. Editing a car never changes its slug, so its URL stays the same.
  - `automotive_site_keys`: a per-tenant **publishable** site key (read-only, revocable), its
    allowed origins, and an optional revalidation webhook URL and secret.
- **Public stock API** (no user session; the key is in `X-Onyx-Site-Key`; read-only; rate
  limited per key and IP; responses cacheable with ETags):
  - `GET /v1/public/stock/vehicles`: filters `make`, `model`, `body`, `fuel`, `transmission`,
    `price_min` and `price_max` (cents), `km_max`, `year_min`, `status` (`available`,
    `reserved` or `sold`; sold covers the last 30 days only), plus `q`, `sort` (`newest`,
    `price_asc`, `price_desc`, `km_asc`) and `page`.
  - `GET /v1/public/stock/vehicles/{slug}`: one vehicle, including sold ones for 30 days.
    Withdrawn vehicles return 410.
  - `GET /v1/public/stock/facets`: makes and models with counts, plus price and year ranges.
  - Fields: `slug`, `stock_number`, `title`, `make`, `model`, `variant`, `year`, `mileage_km`,
    `engine_cc`, `fuel`, `transmission`, `body_type`, `colour`, `doors`, `condition`,
    `price_cents` (null means price on request), `currency`, `features`, `photos` (Onyx-hosted
    URLs of the web versions), `video_url`, `status`, `updated_at`.
- **Revalidation:** when a car is added, or its status, price, details or photos change, Onyx
  calls the site's revalidation URL with the slug, signed with the key's secret, as a retried
  outbox job. The site then updates within seconds, with the 5-minute refresh as the backstop.
- Tests:
  - a two-tenant negative test: a key never sees another tenant's cars;
  - the fields never include the VIN, the deal or anything internal;
  - rate limits and origin checks;
  - the sold and withdrawn rules, and slugs that never change.

### 0c — Public enquiries (later, about 6–10h)

`POST /v1/public/stock/enquiries` takes the name, phone and/or email, message, vehicle slug and
consent.

- It is protected by the site key, the allowed origin, a rate limit, a honeypot field and
  Cloudflare Turnstile.
- It creates an inbox conversation and a lead.
- It is built only once client personal data is allowed in Onyx production (see Enquiries).

Until 0b is live, the site runs on a **fixture adapter**: a JSON snapshot of the stock in the
same shape as the API, chosen by an environment variable. So the site can be designed and built
while part 0 is in progress.

## Enquiries

The Onyx memory notes say no client personal data goes into Onyx production until Supabase is
on a paid plan and a data processing agreement is signed. So:

- **v1:** enquiry forms send an email to Ventur through a dedicated, send-only Resend key, the
  same way as the onyx.mt enquiry form. Nothing is stored by the site.
- **Once allowed:** the same form posts to Onyx's public enquiries endpoint instead, so
  enquiries land in the inbox. This is a switch by environment variable, not a rebuild.
- Every vehicle page also offers WhatsApp (a `wa.me` link with the car's stock number in the
  message) and a call button. Web chat comes with VA-003.
- Spam: a honeypot field, a time-to-submit check, and Cloudflare Turnstile.
- The privacy notice says what is collected, why, and for how long.

## Design

The `/design-taste-frontend` skill (Taste Skill, installed globally) leads the look. Work one
page per run: plan first, then build.

- **Kind:** a car showroom that sells cars, so the skill's "place" plan applies, led by
  photographs: real car photos from the stock, and the showroom if Ventur supplies photos.
- **Brand:** Ventur's own logo and colours through the skill's `start.mjs brand` command. Do not
  use a random palette. The current site's Elementor colours are theme defaults, not the
  brand: take the colours from the logo and confirm them with the owner.
- **Real contact details:** waive the skill's house rule 9 (no real phone, address or contacts)
  in `.taste-skill/waivers.json`, with "the client's real site" as the reason.
- **One system:**
  - The skill's tokens (palette, type, radius, spacing) become the Tailwind theme.
  - The stock pages (search, filters, vehicle page) are built as React components on the same
    tokens. The skill's "one section per screen" rules do not apply to them.
  - The skill's kit is not added as a second CSS system.
- **Its checks:** run the skill's gate against the dev server URL (`--start
http://localhost:3000/`) for the homepage and brand pages.

## Pages

- `/`: the homepage. It shows what Ventur sells, a quick search, the newest cars, finance and
  risk-free import, trust (years, reviews link), the visit block and the contact actions.
- `/search/`: all stock, filtered by URL query (shareable, server-rendered), with the facets,
  sorting, pagination and an empty state.
- `/search/{make}/`: a make's stock (the same page, pre-filtered, with its own title and
  description).
- `/listing/{slug}/`: the vehicle page.
  - A photo gallery: keyboard-accessible, with no carousel autoplay.
  - The key specs, the features, the price or "price on request", and the reserved or sold
    state.
  - A finance estimate using the same formula as Onyx's VA-006 calculator (the API's
    `/finance/estimate` logic, mirrored or called).
  - The enquiry form, WhatsApp and call actions, and similar cars.
- `/sold/`: cars sold in the last 30 days.
- `/loan-calculator/`: the finance calculator, matching Onyx's estimate exactly.
- `/risk-free-import/`, `/about-us/`, `/our-team/`, `/faq/` and `/contact-us/` (with a map
  link, opening hours and the form).
- The two blog posts, kept at their URLs.
- `/privacy/`, and a custom 404 that offers search.

## SEO and the move from WordPress

- Metadata, Open Graph images (a vehicle page uses its first photo), canonical URLs, and
  `noindex` on every non-production deployment.
- Structured data:
  - `AutoDealer` (LocalBusiness) on every page;
  - `Car` with an `Offer` on vehicle pages;
  - `BreadcrumbList`;
  - `FAQPage` on `/faq/`.
- `sitemap.xml` from live stock and the content pages, plus `robots.txt`.
- **Redirects:**
  - The dropped pages go to `/search/` or `/`.
  - The other taxonomy archives map to filtered searches (`/search/?fuel=hybrid` and so on).
  - `/listing/{numeric-id}/` URLs (some exist, for example `/listing/26985/`) go to their slug.
  - Withdrawn or long-sold cars go to their make page.
  - All of these are tested by a script that requests every URL in the old sitemaps
    (saved in the repo as `migration/old-urls.txt`) and expects 200 or a single redirect to a
    200 page.
- Launch checklist: Google Search Console access, submit the new sitemap, watch crawl errors for
  two weeks.

## Build order (one PR each in the `ventur` repo)

1. **Bootstrap:**
   - Next.js, TS strict, Tailwind 4, ESLint and Prettier, Vitest and Playwright.
   - GitHub Actions CI (format, lint, typecheck, test, build, E2E) and a Vercel project with
     previews.
   - A README with the commands, `.env.example`, and `CLAUDE.md` with the workflow rules below.
2. **Stock layer:**
   - A typed client for the public stock API and the fixture adapter, chosen by `STOCK_SOURCE`.
   - The fixture is generated once from Ventur's current WordPress REST API
     (`/wp-json/wp/v2/cars`), anonymised of anything not public.
   - Includes caching, the revalidation route (verifies Onyx's signature) and unit tests.
3. **Design system and homepage** with `/design-taste-frontend`: the homepage plan first, then
   the owner approves it, then the build. The tokens go into Tailwind.
4. **Search and make pages:** filters, facets, sorting, pagination, empty states and E2E tests.
5. **Vehicle page:** the gallery, specs, finance estimate, reserved and sold states, similar
   cars, structured data and E2E tests.
6. **Enquiries:** the form (Resend in v1), WhatsApp and call actions, spam protection, the
   privacy page and tests.
7. **Brand pages:** about, team, FAQ, risk-free import, loan calculator, contact, the two blog
   posts and the 404, each through `/design-taste-frontend` with plan and build.
8. **SEO and migration:** metadata, structured data, sitemap, robots, the redirect map, the
   old-URL check script, and a Lighthouse CI budget.
9. **Launch** (needs the owner's approval for each step):
   - parts 0a and 0b live in Onyx production, and `STOCK_SOURCE=onyx`;
   - a final WordPress import, the photo copy, then the WordPress source turned off in Onyx;
   - Ventur's staff shown how to add cars in Onyx;
   - photos served from Onyx;
   - Ventur approves the content;
   - the DNS cut-over from WordPress to Vercel;
   - Search Console, then two weeks of monitoring;
   - WordPress kept read-only for 30 days, then retired.

## Workflow rules for the `ventur` repo (copy into its `CLAUDE.md`)

- Plan before each PR. Branch inside the repo (no worktrees), one PR per item above.
- PR titles have no numbers. No co-author or attribution lines in commits or PRs.
- Commit, push, open the PR ready for review (not draft), then `gh pr merge --auto --squash`,
  and merge only on green CI.
- No secrets in git: `.env.example` holds placeholders only, and real values go in Vercel and
  the local `.env`.
- Never change DNS, deploy production or create paid accounts without the owner's approval.
- Use only Ventur's own content and photos. No invented reviews, figures or customers, and no
  stock photos passed off as Ventur's. Stand-ins are marked and listed for the owner to replace.

## Owner actions

- [ ] Ventur's approval to rebuild, and who signs off the content.
- [ ] Logo files (SVG if they have it) and brand colours; showroom and team photos.
- [ ] The real phone numbers, WhatsApp number, address, opening hours and email to show. Take
      them from the current site and confirm them with Ventur.
- [ ] Domain and DNS access for ventur.com.mt (who holds it today), for the launch.
- [ ] Hosting: Vercel Pro or the Onyx Studio team (Hobby is non-commercial).
- [ ] A Resend send-only key and the recipient address for enquiries.
- [ ] Cloudflare Turnstile keys for the forms.
- [ ] Google Search Console access for ventur.com.mt.
- [ ] Before enquiries go into Onyx: Supabase on a paid plan and a DPA with Ventur.
- [ ] Ventur's sold-field mapping for the WordPress import (still open from VA-001), needed
      for the import before launch.
- [ ] Storage: check the photo volume after the copy. Supabase's free plan has 1 GB of
      storage, and Ventur's current stock may need the paid plan (which client data needs
      anyway).
- [ ] Who at Ventur adds cars and photos in Onyx, and whether members may edit stock or only
      owners and admins.

## Out of scope (v1)

- Web chat (VA-003), customer accounts, saved searches, car comparison and the map search.
- A CMS for the content pages, and a Maltese translation (both can follow).
- Online payments or reservations.

## Rollback

Until the DNS cut-over, the old site keeps running and nothing changes for visitors. After it,
the rollback is pointing DNS back to the WordPress host, which stays up read-only for 30 days.
