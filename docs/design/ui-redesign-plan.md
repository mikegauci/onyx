# Platform UI redesign plan

Status: **in progress** · Started: 2026-11-24 · Owner request: "the whole UI and UX needs some serious work".

## Decisions (owner, 2026-11-24)

| Question        | Answer                                                                                                           |
| --------------- | ---------------------------------------------------------------------------------------------------------------- |
| Scope           | Every screen in app.onyx.mt.                                                                                     |
| Direction       | Match the onyx.mt site: deep warm black, hairline borders, one orange accent, light display type, mono eyebrows. |
| Process         | Build straight in code, one area per PR, reviewed on Vercel previews. No mockup step.                            |
| Users / devices | Staff on desktop and phones equally: a full desktop layout that collapses well to mobile.                        |

## Ground rules

- Behaviour, permissions and API calls stay the same. This is presentation only, and the backend still decides everything.
- Accessible names, headings, landmarks and roles that the Playwright suite uses stay stable. If one must change, update the spec in the same PR.
- Every PR keeps light mode working and the token contrast tests passing.
- Use the shared pieces from part 1 (`PageHeader`, `Panel`, `DetailList`, `Eyebrow`, `selectClass`, `textareaClass`) instead of one-off classes.
- One primary (orange) button per area. Secondary actions use `outline` or `ghost`.

## Parts

### 1. Foundation: done in PR #56

- Tokens: dark by default, the site's canvas and orange accent.
- Primitives: pill buttons, soft badges, cards, inputs and tables.
- Shell: wordmark, sticky top bar, content width cap.
- Pages: `PageHeader` with pill tabs on every module; redesigned overview, tasks, sign-in and workspace picker.

### 2. Inbox (next)

Conversation page (`m/inbox/conversations/[id]`):

- Messages shown as chat bubbles: customer on the left, staff replies on the right, internal notes full-width and clearly marked. Assistant notes carry their own label and tint.
- A message box (composer) at the bottom of the thread, with the message type as a segmented control.
- Status actions (close, reopen, waiting) in the conversation header, next to the status, channel and customer.
- WhatsApp reply-window notice shown as a compact banner with the time it closes.
- A sidebar that groups Reply for approval, Sales assistant, Details (assignee, handler, CRM contact, lead), and History.
- Mobile: the sidebar stacks under the thread, with the reply panel first.

Conversations list: queue pills, a compact search and filter bar, and rows that show customer, channel, status, assignee and last message time at a glance.

Also: channels, blocked addresses, new conversation form, outbound replies list and draft page.

### 3. Sales records

CRM (leads, contacts, customers, import), catalogue (products, imports, settings), vehicles (list, detail, import) and quotations (list, detail, new, settings):

- Lists: one consistent toolbar (search, filters, primary action), with tables that collapse to cards on phones.
- Detail pages: a header with key facts, `DetailList` panels and an activity timeline.
- Forms: grouped in panels, with labels and help text aligned and one primary action.

### 4. Assistant and knowledge

Sales assistant policies, knowledge documents and search, in the same patterns as part 3.

### 5. Settings, admin and remaining pages

- Workspace settings: general, members, modules, integrations, billing and audit.
- Platform admin: organisations, organisation detail and status.
- Invitation acceptance, the suspended page, the not-found page and the error page.

## Verification for each PR

- `pnpm lint`, `pnpm typecheck`, and unit tests for `@onyx/ui` and the platform.
- Screenshots of the changed screens against the seeded e2e data, at desktop (1440px) and phone (390px) widths.
- Full Playwright suite in CI before auto-merge.
