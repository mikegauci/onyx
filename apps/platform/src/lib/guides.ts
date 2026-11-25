/**
 * The Onyx guides (PR-018): an onboarding guide for new clients and a short operator guide
 * for staff. One source for the in-app Help pages and the PDFs (`pnpm guides:pdf`).
 *
 * Plain data only (no JSX, enums or imports), so the PDF script can load this file with
 * Node's type stripping. Text uses the labels shown in the app; keep them in step with the UI.
 * Written for any client: nothing here is specific to one business.
 */

export type GuideImage = { src: string; alt: string; caption?: string };

export type GuideSection = {
  id: string;
  title: string;
  /** Who this part is for, when it is not everyone. */
  audience?: string;
  intro?: string;
  steps?: string[];
  points?: string[];
  tip?: string;
  image?: GuideImage;
};

export type Guide = {
  slug: "onboarding" | "operator";
  title: string;
  summary: string;
  sections: GuideSection[];
};

const shot = (name: string, alt: string, caption?: string): GuideImage => ({
  src: `/guides/${name}.png`,
  alt,
  caption,
});

export const ONBOARDING: Guide = {
  slug: "onboarding",
  title: "Getting started with Onyx",
  summary:
    "A step-by-step tour of Onyx for a new business: setting up, the inbox, the assistant, replies, quotes and the tools for checking how it is going.",
  sections: [
    {
      id: "how-it-works",
      title: "How Onyx works",
      intro:
        "Onyx brings every customer enquiry into one inbox, helps your team answer quickly and keeps a record of what happened.",
      steps: [
        "A customer writes on WhatsApp or email, or calls and nobody answers. The message lands in the Inbox.",
        "Staff, or the sales assistant on request, prepare a reply. The assistant checks prices, stock and your policies before it suggests anything.",
        "An owner or admin approves the reply. Only then can it be sent.",
        "The conversation, the reply and any quote stay linked to the customer's record.",
      ],
      tip: "Nothing reaches a customer without a person approving it, unless your business has agreed an automatic-reply policy with Onyx.",
    },
    {
      id: "sign-in",
      title: "Signing in and roles",
      steps: [
        "Open the invitation link you were sent and sign in with the same email address.",
        "Next time, go to app.onyx.mt and sign in with your email.",
        "If you belong to more than one business, pick it from the switcher at the top of the sidebar.",
      ],
      points: [
        "Owner: everything, including billing and members.",
        "Admin: settings, channels, approving replies and quotes, pilot controls.",
        "Member: reads and answers conversations, drafts replies and quotes, uses the assistant. Members cannot approve.",
      ],
    },
    {
      id: "overview",
      title: "Finding your way around",
      intro:
        "The sidebar lists Overview, Insights, Tasks, the modules on your plan and Settings. On a phone, open it with the menu button at the top.",
      points: [
        "Overview shows what needs your attention: open tasks and each module at a glance.",
        "Tasks counts the reminders waiting for you, such as a reply to approve or a missed call to return.",
        "The sun and moon button switches between light and dark.",
      ],
      image: shot("overview", "The Overview page with open tasks and module cards"),
    },
    {
      id: "workspace-setup",
      title: "Setting up your workspace",
      audience: "Owners and admins",
      steps: [
        "Settings → General: check the name, timezone and brand colour.",
        "Settings → Members: invite each staff member with the right role. Each invitation is a one-time link.",
        "Settings → Billing (owners): check the plan.",
        "Settings → Audit log: see who changed what, at any time.",
      ],
    },
    {
      id: "channels",
      title: "Connecting your channels",
      audience: "Owners and admins",
      intro:
        "Inbox → Channels lists where messages come from. Onyx support connects WhatsApp numbers and phone lines for you; you look after the details.",
      steps: [
        "Email: use the forwarding address shown for the channel, and set the sender name and signature customers will see.",
        "WhatsApp: check the number shows as connected. Press “Refresh from WhatsApp” after Meta approves a new message template.",
        "Phone and walk-ins: use “Record conversation” to log a call or visit by hand, so it is part of the history.",
        "Missed-call text-back (if set up): forward unanswered calls to the number shown. Choose the WhatsApp template and the SMS text, then press “Save text-back settings”.",
      ],
      tip: "Inbox → Blocked addresses lists people who replied STOP or whose email bounced. Onyx will not message them.",
    },
    {
      id: "inbox",
      title: "Working in the inbox",
      intro:
        "Inbox → Conversations shows every conversation, newest first. Search by name, subject, phone or email, or filter by status, channel or who it is assigned to.",
      steps: [
        "Open a conversation to see the whole thread, oldest at the top.",
        "Assign it to yourself or a colleague, and link it to a contact so the history follows the customer.",
        "Write your answer in the “Reply for approval” panel and press “Save for approval”. An owner or admin approves it before it can go out.",
        "Use “Add an internal note” for anything only staff should see. “Log a reply” records an answer you already gave by phone or in person.",
        "Keep the status up to date: Open while you are working on it, waiting on customer when the ball is in their court, and closed when it is done. Change it in the conversation header, or pick it under “Then” when you save a reply.",
      ],
      points: [
        "WhatsApp only allows free text for 24 hours after the customer's last message. After that, Onyx offers your approved templates.",
        "A missed call appears in the caller's thread as “Missed call”, with an urgent task to call back.",
      ],
      image: shot(
        "conversation",
        "A conversation with messages, the reply box and the details panel",
      ),
    },
    {
      id: "contacts",
      title: "Contacts, customers and leads",
      points: [
        "Contacts are people. Customers are businesses or households that contacts belong to.",
        "Leads track a sales opportunity from new to won or lost, with a reason when it is lost.",
        "Import contacts from a CSV file under CRM → Import. Onyx shows a preview before anything is saved.",
      ],
    },
    {
      id: "stock",
      title: "Your stock: vehicles and products",
      intro:
        "The assistant only offers what is in Onyx, so keep stock up to date. Depending on your plan you have Vehicles, the Catalogue, or both.",
      steps: [
        "Vehicles → Import from website: enter your website address and press “Preview import”. Check the changes, then press “Import these changes”. Run it again whenever stock changes; nothing is duplicated.",
        "A sold, reserved or withdrawn car is never offered as available.",
        "Catalogue: products, prices, price lists and VAT rates. Import a CSV under Catalogue → Import.",
      ],
      image: shot("vehicles", "The vehicles list with prices, mileage and status"),
    },
    {
      id: "knowledge",
      title: "Knowledge: documents the assistant can use",
      steps: [
        "Knowledge → Documents → “Upload document”: add brochures, warranty terms, opening hours or FAQs (PDF or text).",
        "Use Knowledge → Search to check what the assistant would find for a question.",
        "When the assistant uses a document, its note lists the source so you can check it.",
      ],
    },
    {
      id: "assistant",
      title: "Using the sales assistant",
      steps: [
        "In a conversation, press “Draft with assistant”. It takes up to 30 seconds.",
        "If everything checks out, the assistant adds a draft reply as a note and, when the customer asked for a price, a draft quote.",
        "If anything is uncertain, such as a price negotiation, finance, a complaint or missing stock, it hands the conversation to staff and lists why.",
        "Turn the note into a reply, edit it as needed and save it for approval.",
      ],
      points: [
        "The assistant never sends anything itself and never invents prices: totals come from your price list.",
        "Owners and admins can add short policy texts (delivery, warranty, opening hours) on the Assistant page. The assistant quotes them word for word.",
      ],
    },
    {
      id: "approvals",
      title: "Replies and approvals",
      intro:
        "Outbound replies has three lists: “Waiting for approval”, “Approved, ready to send” and “Recently sent”.",
      steps: [
        "Open a reply waiting for approval and read it next to the conversation.",
        "If it is right, press “Approve reply”, or “Approve and send” to send it straight away.",
        "To change it, edit the text and press “Approve edited text”. The edit is kept as a new version.",
        "If it is wrong, reject it with a short reason. Nothing is sent.",
      ],
      points: [
        "A reply expires if the customer writes again, the quote changes or it waits too long, so nobody sends an out-of-date answer.",
        "Approvers get a reminder task after a few hours, and an urgent one later. Owners and admins set the timings on the Outbound replies page.",
      ],
      image: shot("replies", "The replies waiting for approval"),
    },
    {
      id: "quotes",
      title: "Quotes",
      steps: [
        "Quotations → “New quote”, or start from the assistant's draft quote. Pick the contact, then add lines from your stock or custom lines such as delivery.",
        "Press “Create draft quote”. Totals and VAT are worked out by Onyx.",
        "An owner or admin presses “Approve quote”. Only an approved quote can be included in a reply.",
        "When the customer decides, press “Record accepted” or “Record declined”. To change an approved quote, use “Revise (new version)”.",
      ],
      image: shot("quote", "A quote with its lines, totals and actions"),
    },
    {
      id: "deals",
      title: "Deals and documents",
      intro:
        "A deal follows one sale from reservation to collection: reserved, deposit received, documents, finance (for financed sales), sold and collected.",
      steps: [
        "Deals → “New deal”: choose the customer and, if you sell cars, the car. The car is marked reserved, so the assistant stops offering it.",
        "Record the deposit when it is paid (amount, date and method). Onyx never takes money itself.",
        "Collect the documents on the checklist. Upload what the customer gives you, or press “Request documents” to send them a private link (valid 7 days) where they can take photos with their phone.",
        "An owner or admin opens each document and verifies it, or rejects it with a reason so the customer can send it again.",
        "When everything is verified, move the deal to sold, then to collected when the customer drives away.",
      ],
      points: [
        "A deal cannot be marked sold while required documents are not verified. An owner can override this with a reason, which is recorded.",
        "Onyx adds tasks for you: checking documents that arrived, and chasing customers whose documents are still missing after two days.",
        "Document files are deleted automatically some time after a deal is collected or cancelled (180 days unless you change it under Deals → Settings). The deal record stays.",
      ],
      image: shot("deal", "A deal with its document checklist, stage and details"),
    },
    {
      id: "finance",
      title: "Finance",
      intro:
        "Deals → Finance works out monthly payments with the same calculation as your website's loan calculator, and keeps each customer's finance application.",
      steps: [
        "Use the calculator for a quick estimate: price, deposit and years.",
        "On a deal, press “Start a finance application”. Choose the applicant type and marital status; the deal's checklist switches to the documents that applicant needs, including the spouse's when married.",
        "Send the customer the upload link: the KYC & Loan Request and CCR forms can be downloaded right next to their checklist items.",
        "Owners and admins record income details and the decision (approved or declined). Onyx never approves or declines finance.",
      ],
      points: [
        "When a customer asks about paying monthly, the sales assistant can draft a reply with the estimate and start the application. Its reply always says it is an estimate, and it never promises approval or a rate. You approve the reply before it is sent.",
        "Set the rates, the term range, the disclaimer and the PDF forms under Deals → Settings.",
      ],
    },
    {
      id: "tasks",
      title: "Tasks",
      points: [
        "Onyx creates tasks for you: replies waiting for approval, missed calls to return and urgent follow-ups.",
        "Open a task to go straight to what it is about, then press “Mark done”.",
        "Urgent tasks are marked, so they stand out.",
      ],
    },
    {
      id: "insights",
      title: "Insights: how it is going",
      intro:
        "Insights shows the last 7, 30 or 90 days. It is worked out from your records; no message text is used.",
      points: [
        "Enquiries by channel, and enquiries per week.",
        "Median first reply: how long customers wait for a reply from a person. Automatic messages are not counted.",
        "Assistant replies: sent as written, edited, rejected or expired, and how long approval takes.",
        "Hand-offs to staff and the most common reasons.",
        "Quotes: created, approved, sent and accepted.",
        "Missed calls and their text-backs.",
      ],
      tip: "Owners and admins can enter “before Onyx” figures under Settings → Pilot controls, so Insights shows the change.",
      image: shot("insights", "The Insights page with enquiries, response time and replies"),
    },
    {
      id: "pilot-controls",
      title: "Pilot controls and manual mode",
      audience: "Owners and admins",
      intro:
        "Settings → Pilot controls lets you pause parts of Onyx at once, without a call to support.",
      points: [
        "Feature switches pause the sales assistant or missed-call text-back for your business only.",
        "Manual mode means humans only: nothing is drafted or sent automatically. Messages still arrive and staff reply as normal. A banner shows on every page while it is on.",
        "Turning manual mode off restores the switches as they were. Every change is in the audit log.",
      ],
      image: shot("pilot-controls", "The Pilot controls settings with manual mode and switches"),
    },
    {
      id: "help",
      title: "Getting help",
      points: [
        "Help in the sidebar has this guide and the operator quick reference.",
        "If something fails, Onyx shows a “Reference” code. Send that code to your Onyx contact.",
        "Never paste customer messages or personal details into email or chat with support; the reference is enough.",
      ],
    },
  ],
};

export const OPERATOR: Guide = {
  slug: "operator",
  title: "Operator quick reference",
  summary:
    "The daily routine for staff who answer customers in Onyx, and what to do when something looks wrong.",
  sections: [
    {
      id: "daily",
      title: "Your daily routine",
      steps: [
        "Open Overview: deal with anything under “Needs your attention” first.",
        "Tasks: urgent items first, such as missed calls and replies waiting too long.",
        "Inbox: work through open conversations, oldest first. Assign each one you take.",
        "Approvers: clear “Waiting for approval” under Outbound replies at least every few hours.",
        "Before you leave: set each conversation you touched to waiting on customer, or close it.",
      ],
    },
    {
      id: "enquiry",
      title: "Answering an enquiry",
      steps: [
        "Open the conversation and read the whole thread.",
        "Link it to the customer's contact if it is not linked yet.",
        "Press “Draft with assistant”, or write the reply yourself.",
        "Check the draft, edit if needed and save it for approval.",
        "Once it is approved, press “Send reply”, unless the approver already sent it.",
      ],
    },
    {
      id: "check",
      title: "Before you approve",
      points: [
        "Price, car or product and availability match what Onyx shows.",
        "Nothing is promised about finance, trade-in values or warranties unless your policy says so.",
        "The tone suits the customer, and the reply answers what they asked.",
        "If in doubt, reject with a reason or edit it. Rejecting sends nothing.",
      ],
    },
    {
      id: "missed-calls",
      title: "Missed calls",
      points: [
        "Each missed call creates an urgent “Call back” task and a “Missed call” message in the caller's thread.",
        "If text-back is on, the caller has already received a message inviting them to reply on WhatsApp. Their reply lands in the same thread.",
        "Call back, note what was agreed and mark the task done.",
      ],
    },
    {
      id: "handoff",
      title: "When the assistant hands over",
      points: [
        "The assistant's note says why: for example, no price, not enough stock, or the customer asked for a person.",
        "Answer it yourself. Don't ask the assistant again until the cause is fixed, such as a missing price.",
      ],
    },
    {
      id: "deals",
      title: "Deals and documents",
      points: [
        "When a customer says yes, create the deal straight away so the car is reserved.",
        "Use “Request documents” to send the customer their upload link, or upload what they hand you.",
        "“Chase documents” tasks list deals still missing documents; follow them up the same day.",
        "Only owners and admins open and verify documents. Never forward customer documents by email or chat.",
      ],
    },
    {
      id: "finance",
      title: "Finance questions",
      points: [
        "Give estimates from Deals → Finance, never from memory, and always say it is an estimate.",
        "Never tell a customer they are approved or promise a rate; Ventur's finance team decides.",
        "Check the assistant's finance replies before approving: the amounts and the disclaimer.",
      ],
    },
    {
      id: "manual-mode",
      title: "Manual mode",
      points: [
        "When the banner says “Manual mode is on”, Onyx is not drafting or sending anything automatically.",
        "Keep working as normal: read, reply, approve and send by hand.",
        "Owners and admins switch it under Settings → Pilot controls. Use it when anything automatic looks wrong.",
      ],
    },
    {
      id: "wrong",
      title: "If something looks wrong",
      steps: [
        "Don't send it. Reject the reply, or turn on manual mode if you are an owner or admin.",
        "Write down the “Reference” code if Onyx shows one.",
        "Tell your Onyx contact what happened and when, with the reference. Don't paste customer details.",
      ],
    },
  ],
};

export const GUIDES: Guide[] = [ONBOARDING, OPERATOR];

export function guideBySlug(slug: string): Guide | undefined {
  return GUIDES.find((g) => g.slug === slug);
}
