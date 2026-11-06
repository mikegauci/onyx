# Sales assistant (PR-015)

Staff ask the assistant to draft a reply and a quote for an inbox conversation. The assistant
reads the thread, looks things up with read-only tools, and proposes a draft. **Deterministic
backend rules decide** whether that proposal becomes a draft quote or goes to staff. Nothing is
ever sent to a customer: the reply is an internal note and the quote stays a draft until staff
approve it (sending is PR-016/PR-017).

The `assistant` module requires `inbox`, `catalogue` and `quotations`. A platform admin enables
it per tenant, and the tenant needs an AI budget (see [ai-gateway.md](ai-gateway.md)).

| Permission         | Roles                | Allows                                    |
| ------------------ | -------------------- | ----------------------------------------- |
| `assistant.run`    | member, admin, owner | Run the assistant; list runs and policies |
| `assistant.manage` | admin, owner         | Create, edit and delete policy texts      |

## A run

1. Refused (`409`, no cost) if the conversation is closed or has no customer message.
2. The model gets the instructions, the last 20 customer/shop messages as **quoted data** in a
   `<customer_thread>` block (angle brackets in messages are neutralised so text cannot break
   out), and three tools, all read-only and bound to the tenant:
   - `search_products(query)`: up to 10 active SKUs with price on the default list, VAT rate,
     stock and when stock was observed.
   - `check_stock(skus)`: latest stock per SKU, or unknown. Never zero by default.
   - `get_policy(topic)`: the tenant's written policy, or "not on record".
3. The model returns a structured proposal: `draft_quote` or `escalate`, lines (SKU, quantity),
   a reply draft, confidence and the policies it relied on.
4. The rules check it against what the tools returned **in this run** and the catalogue **as it
   is now**. Any of these sends it to staff, with no quote:

   | Reason                                                 | When                                                     |
   | ------------------------------------------------------ | -------------------------------------------------------- |
   | `model_escalated`                                      | The model asked for a person                             |
   | `low_confidence`                                       | The model said it was unsure                             |
   | `no_lines`                                             | Nothing to quote                                         |
   | `ungrounded_sku`                                       | A SKU no tool returned in this run                       |
   | `unknown_sku`                                          | Not in this tenant's catalogue                           |
   | `archived_sku`                                         | Archived product or SKU                                  |
   | `missing_price`                                        | No price on the default price list                       |
   | `missing_vat`                                          | The product has no VAT rate                              |
   | `unknown_stock`                                        | No stock observation                                     |
   | `insufficient_stock`                                   | Quantity above available stock                           |
   | `reply_mentions_amount`                                | The reply states a price, amount, percentage or discount |
   | `reply_ungrounded_sku`                                 | The reply names a SKU no tool returned                   |
   | `unknown_policy`                                       | Relies on a policy it did not find this run              |
   | `no_contact`                                           | The conversation has no CRM contact                      |
   | `quote_failed`                                         | The quotations service refused the draft                 |
   | `budget_exceeded`, `ai_unavailable`, `provider_failed` | The AI call did not happen or failed                     |

5. If every check passes, the backend creates a **draft quote** through the quotations service
   (default price list, no discounts; numbering, price snapshots, VAT and totals exactly as for
   staff-made quotes) and adds a note with the draft reply. Otherwise it adds a note listing the
   reasons, and if the assistant was handling the conversation, hands it back to staff.
6. The run is recorded in `assistant_runs` (outcome, reasons, tool names and returned SKUs, the
   usage event, cost, quote and note) and audited as `assistant.run.drafted` or
   `assistant.run.escalated`. Message text and tool output are not stored in the run.

With the `outbound` module on (PR-016), a drafted run also files its reply as a pending draft
that an approver must approve, after the quote, before it is sent. See [outbound.md](outbound.md).

Staff start runs; nothing runs automatically on new messages yet (that needs the worker in
PR-020). A run makes several model requests inside one API request, so it can take 10–30 s.

## Screens

- **Inbox conversation:** a "Sales assistant" panel in the right column, shown when the module
  is on and the user has `assistant.run`. "Draft with assistant" starts a run (disabled while
  it works and on closed conversations; the API refuses other cases with a message). The panel
  lists the last 5 runs with outcome, quote link, reasons and cost. The assistant's note shows
  in the thread as "Internal note by Assistant".
- **Sales assistant page** (`/w/{slug}/m/assistant`): what the assistant does and the policy
  list. Admins and owners (`assistant.manage`) add, edit and delete policies; members read them.

The dashboard only displays. Reasons come from the API as `{code, message}`, so their wording
lives in one place (`REASON_TEXT` in `rules.py`).

## API

| Route                                                       | Permission         |
| ----------------------------------------------------------- | ------------------ |
| `POST /v1/w/{slug}/assistant/conversations/{id}/runs`       | `assistant.run`    |
| `GET /v1/w/{slug}/assistant/conversations/{id}/runs`        | `assistant.run`    |
| `GET /v1/w/{slug}/assistant/policies`                       | `assistant.run`    |
| `PUT /v1/w/{slug}/assistant/policies/{topic}` (title, body) | `assistant.manage` |
| `DELETE /v1/w/{slug}/assistant/policies/{topic}`            | `assistant.manage` |

Topics are lower-case slugs (`delivery`, `returns`, `warranty`, `lead_times`).

## Evaluations

- **In CI (no cost):** `tests/modules/assistant/test_rules.py` covers every rule and the prompt
  boundary; `tests/api/test_assistant.py` scripts the model request by request against the real
  tools, database and rules. It covers a grounded draft, each escalation reason, a tricked model
  (prompt injection naming another tenant's SKU, a discount and a fake total), AI failures, the
  module gate, roles and two-tenant isolation.
- **Live (opt-in, costs money):** `make eval-assistant yes=1` runs 16 fixed cases
  (`apps/api/evals/assistant_cases.py`) against the configured real model with a fixture
  catalogue and the same rules, and prints pass/fail per case and the estimated spend. It needs
  the model, its price and key in `.env`. Run it only with the owner's approval.

## Rollback

Revert the PR and disable the module for tenants. Migration `0014` downgrades locally (drops
both tables, removes the module and restores the note rule) and refuses while assistant notes
exist, because messages are append-only. Deployed databases use a forward fix or a backup
restore.
