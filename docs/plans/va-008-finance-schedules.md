# VA-008 — In-house finance schedules and reminders

Status: merged (#94, #96). Depends on VA-006 (finance applications) and VA-007 (deals), both
merged.

## Owner decisions (2026-11-26)

- **Source of payment records:** unknown for now (spreadsheet, accounting software or paper).
  Staff therefore enter each schedule and each payment in Onyx. An import can be added once
  the source is known. Onyx never takes payments.
- **Sending:** as with every other customer message, reminders wait in a list for staff to send.
  The wording and the timing are set by staff, and a schedule's reminders can be paused.

## Part 1 — schedules and payments (migration 0041)

### Data

- `finance_schedules`:
  - links: the contact, plus an optional deal (one schedule per deal) and an optional finance
    application;
  - the car (`label`), the amount to repay (`total_cents`), the term in months, the monthly
    amount and the first due date;
  - `status` (`active`, `completed` or `cancelled`), `reminders_paused` and a note.
- `finance_installments`: one per month (`number`, `due_on`, `amount_cents`). Each is the
  monthly amount; the last one takes the rounding difference, so the installments add up
  exactly to the total. Staff can change one installment's date or amount.
- `finance_payments`: the amount, the date received, the method (`cash`, `bank_transfer`,
  `card`, `cheque` or `other`) and a note, recorded by staff. A mistake is voided with a
  reason, never deleted.

All three tables are gated by the `deals` module and use tenant RLS with same-tenant foreign
keys. Money is in integer cents.

### Rules (pure, unit-tested)

- Payments pay the installments in order, oldest first, so a payment can cover more than one
  installment or part of one.
- Each installment is `paid`, `part_paid`, `overdue` (due before today and not fully paid),
  `due_today` or `upcoming`.
- A schedule shows the amount paid, the amount outstanding, its next due installment and what
  is overdue. It becomes `completed` once everything is paid, and goes back to `active` if a
  payment is voided.

### Creating a schedule

From a financed deal: the amounts are prefilled from its approved application's estimate
(total, term and monthly amount), and staff confirm the first due date. Staff can also enter
a schedule for a customer who financed before Onyx.

### Permissions

- Seeing schedules: `deals.read`.
- Creating and changing schedules, and recording or voiding payments: `finance.manage` (owners
  and admins).

### Dashboard

- Deals → Finance → **Schedules**: every active schedule with its next due date and anything
  overdue, filterable to overdue only.
- The schedule page: installments with their state, payments, and forms to record and void a
  payment.
- The deal page: "Set up payment schedule" on a financed deal.

## Part 2 — reminders (migration 0042)

As built: the before-due reminder can be created from the set number of days before the due
date until the date itself, and the overdue one from the set number of days after it for 30
days. The reminder list shows what is still owed now. Settings are under Deals → Settings
(`deals.manage`). Sending needs `outbound.approve`. The scheduler uses the UTC date.

- `finance_reminders`: one per installment and kind: `before_due`, created a set number of days
  before the due date (default 3), and `overdue`, created a set number of days after it
  (default 3). Only unpaid installments of active, unpaused schedules get one.
- Staff send them from a **Payment reminders** list, the same way as other reminders: WhatsApp
  first (free-form inside 24 hours, else an approved utility template), then email. A
  reminder whose installment is paid in the meantime is skipped.
- `finance_reminder_settings`: the days and, for each kind, the wording and the WhatsApp
  template. The wording is staff-controlled.
- Pausing a schedule dismisses its pending reminders.

## Tests

- Rules: allocation in order, partial payments, overpayment, rounding, and installment states
  around the due date.
- API:
  - creating a schedule from an application;
  - recording and voiding payments;
  - completing a schedule;
  - permissions (members cannot record payments);
  - a two-tenant negative test on every endpoint;
  - RLS, EXPECTED_TABLES, model drift and the OpenAPI contract;
  - privacy export and erase (amounts stay, the note goes, as for finance applications).
- Part 2:
  - the reminder windows;
  - paid installments create no reminder;
  - pause;
  - send once;
  - opt-out.

## Owner actions

- Find out where Ventur keeps payment records today, so an import can follow.
- Enter the existing financed customers' schedules (Deals → Finance → Schedules).
- Optional WhatsApp **utility** templates for the before-due and overdue reminders (part 2).

## Rollback

The migration downgrade drops the new tables. No existing table changes.
