# VA-006: finance pre-qualification, implementation plan

Status: **approved 2026-11-25** · 2026-11-25 · Roadmap: `docs/roadmap-additions.md` (VA-006)

## What Ventur does today (ventur.com.mt/loan-calculator, read 2026-11-25)

**The calculator**

- Inputs: vehicle price, deposit, years (in half-year steps) and the vehicle.
- It uses simple interest, with values set in the page's script:
  - an annual interest rate of **6.5%**;
  - an onboarding fee of **4%** of the net loan;
  - a financing & maintenance fee of **1% a year** of the net loan.
- The formula:
  - net loan = price − deposit;
  - interest = net loan × 6.5% × years;
  - financing & maintenance fee = net loan × 1% × years;
  - onboarding fee = net loan × 4%;
  - total = net loan + interest + financing & maintenance fee + onboarding fee;
  - monthly payment = total ÷ (years × 12).
- It also shows "pay off early and save": the interest and maintenance fee not charged if the
  loan is settled after fewer years.
- Its rules: the price must be above 0, the deposit can't be negative or exceed the price, the
  years must be above 0, and the net loan must be above 0.
- The disclaimer: "This calculator provides an estimate only. Final finance terms may vary."
  Final approval, rates and terms are subject to finance provider checks, documents and
  approval.

**The application**

- The applicant chooses their type and marital status, and gives their name, phone and the
  vehicle they want. They accept the Privacy Policy and Terms.
- The site then shows the checklist for that applicant type and the forms to download. The
  customer **emails everything to info@ventur.com.mt**.

**Forms (PDF)**

- KYC & Loan Request Form (personal details, employment, source of funds, the loan request,
  existing commitments, declarations; a second party where applicable).
- CCR Form (consent to a Central Credit Register check; the spouse or second party signs too).
- Documents Required checklist.

**Required documents by applicant type**

- **Maltese resident:** ID card, vehicle licence, the last 3 months' payslips, the latest FS3,
  the KYC & Loan Request Form and the signed CCR Form.
- **Non-Maltese resident:** ID or residence card, vehicle licence, passport, the last 3 months'
  payslips, the latest FS3, work contract, JobsPlus history, rental agreement (if any), KYC and
  CCR.
- **Self-employed:** ID card, vehicle licence, passport (if not a Maltese resident), the last 2
  years' P&L and income tax returns signed and stamped by an accountant, rental agreement (if
  any), KYC and CCR.
- **Company:** audited or management accounts for 2 years, the Memorandum & Articles,
  Certificate of Incorporation, a board resolution, ID and proof of address for every
  shareholder, the surety's last 3 payslips and latest FS3, the Malta Business Registry
  certificate of beneficial owners, KYC and CCR.
- **Married applicants** (every type except company): the spouse's matching documents and
  signatures on the KYC and CCR forms. The site warns that incomplete spouse documents delay
  or stop the application.

## What Onyx will do

1. **Finance settings per workspace** (owners), pre-filled with Ventur's figures:
   - the rate, onboarding fee and yearly fee, plus the minimum and maximum term;
   - the disclaimer;
   - the forms: Onyx links to Ventur's PDFs or keeps a copy;
   - the checklist for each applicant type, with the extra spouse items.
2. **One finance estimate, worked out by the API.**
   - It uses the same formula as the website, in exact cents with no floating point.
   - It shows the monthly payment, a breakdown and the early-payoff saving, always with the
     disclaimer.
   - A test checks the result against the website for the same inputs.
   - Staff, deals and the assistant all use this one calculation.
3. **A finance application** linked to the contact, and to the deal and car where there is
   one:
   - **Details:** the applicant type, marital status, price, deposit, term and the stored
     estimate.
   - **Optional details:** employer, net monthly income and existing commitments.
   - **Status:** started → documents → submitted to provider → approved, declined or
     withdrawn. Staff record approvals and declines; Onyx never decides.
   - **Visibility:** only staff allowed to see finance details can open it (see question 3).
   - **Retention:** the same retention and erase rules as the rest of the person's data.
4. **Deals:**
   - Marking a deal financed links its application. The checklist then follows the applicant
     type: the Maltese-resident list, for example, plus the spouse items when married. This
     replaces the single "Finance papers" item.
   - The KYC and CCR forms become checklist items, with a link to download the blank form.
   - The customer upload page (VA-007) shows those download links next to the items, so
     customers stop emailing documents to info@.
5. **In conversations (the assistant):**
   - When a customer asks about finance, the assistant collects the applicant type, marital
     status, the car (from stock), the deposit and the term. Where you allow it, it gives the
     website's estimate, clearly labelled as an estimate.
   - It sends the link to the checklist and forms, and creates the finance application with a
     summary for the finance clerk.
   - It never approves, declines, negotiates or promises a rate. It hands over any question
     about eligibility, rates or credit history. Incomplete answers are flagged for staff.
6. **Insights:** finance applications started, how many reached documents, and how many were
   submitted, approved or declined.

## Tests

- The estimate matches the website for a set of inputs (half-years, a zero deposit, rounding),
  and refuses the same invalid inputs.
- Each applicant type and marital status gives the right checklist on a financed deal.
- Permissions: staff without finance access can't see income or the application. Another
  tenant's application behaves as missing.
- Assistant evaluation cases, in English and Maltese:
  - a finance question gets the estimate and the forms (or only the forms, if estimates are
    off);
  - "am I approved?", "can you do 4%?" and "I have bad credit" are handed over;
  - prompt-injection attempts to change the rate are refused.
- Erasing a person and retention cover finance applications.

## Owner decisions (2026-11-25)

| Question                 | Decision                                                                                                                                                                                                                                       |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Estimate in chat         | **Yes, as an estimate.** It uses the website's formula and is always labelled with the disclaimer. The assistant never approves, negotiates or promises a rate. This is the one agreed exception to "the assistant never quotes credit terms". |
| Who decides              | **Ventur in-house.** "Submitted to provider" becomes "with Ventur finance". VA-008's payment schedules follow from an approved application.                                                                                                    |
| Who sees finance details | **Owners and admins** (a new `finance.read` permission). Members see that an application exists and its status, not income or employment.                                                                                                      |
| Forms                    | **Copies kept in Onyx**, uploaded once by an owner under Deals → Settings. Links keep working after the site rebuild.                                                                                                                          |

## Parts

1. Settings, the estimate, finance applications, deal checklists by applicant type, the
   dashboard and the tests.
2. The assistant's finance conversation, the evaluation cases, Insights and the guides.

## Not in this work

- Submitting to a finance provider electronically, credit checks, e-signatures, payment
  schedules (VA-008).

## Changes during implementation (part 1)

- **Permission:** `finance.manage` (owners and admins). It shows the income details and decision
  notes, records approvals and declines, and reopens closed applications.
- **Rates:** stored as basis points (650 = 6.5%). The estimate is worked out in exact decimals
  and rounded half up to the cent at the end. A test reproduces the website's example: €16,500
  with €3,000 down over 5 years gives €318.38 a month.
- **Terms:** in half years, 6 to 120 months by default; owners can change the range.
- **Checklist items:** a financed deal with an application gets the applicant type's documents
  (`fin_…` keys, and the spouse's when married). They replace the generic "Finance papers" item.
  The KYC and CCR items link to the blank forms, both on the deal and on the customer upload page.
- **Privacy:** export includes finance applications. Erasing a person clears their employer,
  income, notes and decision note, and keeps the figures.
