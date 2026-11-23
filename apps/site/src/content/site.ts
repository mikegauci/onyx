/**
 * Copy and settings for the Onyx Studio landing page, kept in one place so the owner can review
 * and change wording without touching layout code. No testimonials, client logos, prices or
 * invented statistics are shown until the owner supplies real ones.
 */
export const site = {
  name: "Onyx Studio",
  shortName: "onyx",
  tagline: "AI that answers, books and follows up. People who stay in charge.",
  description:
    "Onyx Studio is a Malta studio building AI automation, websites and integrations for growing businesses, on top of our own platform, Onyx Platform.",
  contactEmail: "info@onyx.mt",
  location: "Malta",
} as const;

export const nav = [
  { label: "Studio", href: "#studio" },
  { label: "System", href: "#system" },
  { label: "Industries", href: "#industries" },
  { label: "Process", href: "#process" },
  { label: "FAQ", href: "#faq" },
] as const;

export const hero = {
  eyebrow: "AI automation studio · Malta",
  lines: ["Intelligence", "that works the", "front desk."],
  body: "We connect your WhatsApp, inbox, website and stock to one AI-assisted workspace, so every enquiry gets a fast, accurate answer, and your team only steps in where it matters.",
  primary: "Start a project",
  secondary: "See the system",
} as const;

/** Read word by word as the visitor scrolls. */
export const statement =
  "Most businesses don't need more software. They need the enquiries, bookings and follow-ups they already have to stop slipping through the cracks. That is the only problem we solve.";

export const system = {
  eyebrow: "The system",
  title: "Every channel in. One brain. Every answer checked.",
  body: "Messages arrive from wherever your customers are. Onyx reads them against your real stock, prices and policies, drafts the reply and routes anything sensitive to a person before it goes out.",
  inputs: ["WhatsApp", "Email", "Web chat", "Missed calls", "Instagram"],
  outputs: [
    "Stock & listings",
    "Bookings",
    "Customer records",
    "Payments & deposits",
    "Staff approval",
  ],
  core: "Onyx",
  notes: [
    {
      title: "Grounded",
      body: "Answers come from your own catalogue and policies. If the data isn't there, the assistant says so and asks a person.",
    },
    {
      title: "Supervised",
      body: "Prices, finance, complaints and anything uncertain are held for approval. Routine replies can be sent automatically once you allow it.",
    },
    {
      title: "Recorded",
      body: "Every draft, edit and approval is logged, so you can see exactly what was said and who signed it off.",
    },
  ],
} as const;

export const services = [
  {
    title: "AI assistants",
    body: "Assistants that reply on WhatsApp, email and web chat in your tone, from your data, around the clock.",
    tags: ["Enquiry replies", "Lead qualification", "Booking"],
  },
  {
    title: "Workflow automation",
    body: "Follow-ups, reminders, document chasing and hand-offs that run on schedule instead of on memory.",
    tags: ["Reminders", "Follow-ups", "Hand-offs"],
  },
  {
    title: "Websites that sell",
    body: "Fast, accessible websites wired to your stock and your inbox, not brochures that sit apart from the business.",
    tags: ["Next.js", "Listings", "SEO"],
  },
  {
    title: "Integrations",
    body: "Your existing tools (website, payments, calendars, spreadsheets) joined up so data is typed once.",
    tags: ["WhatsApp Business", "Stripe", "WordPress"],
  },
] as const;

export type Industry = {
  slug: string;
  name: string;
  headline: string;
  pain: string;
  workflows: readonly string[];
};

export const industries: readonly Industry[] = [
  {
    slug: "car-dealerships",
    name: "Car dealerships",
    headline: "Every stock enquiry answered before the buyer calls someone else.",
    pain: "Buyers message three dealers at once about the same car. The first accurate answer usually wins the viewing.",
    workflows: [
      "Instant replies on availability, mileage and specs, read from your live stock",
      "Viewing and test-drive booking straight into the calendar",
      "Finance and trade-in questions routed to a salesperson",
      "Sold-car alerts and follow-ups for buyers who missed out",
    ],
  },
  {
    slug: "property-agencies",
    name: "Property agencies",
    headline: "From portal enquiry to booked viewing without the phone tag.",
    pain: "Leads arrive from portals, socials and the website at all hours, and most go cold before an agent replies.",
    workflows: [
      "Qualify buyers and tenants on budget, area and timing",
      "Match enquiries to listings and suggest alternatives",
      "Book viewings around agent availability",
      "Chase documents and keep landlords updated",
    ],
  },
  {
    slug: "restaurants",
    name: "Restaurants",
    headline: "Reservations, questions and events handled while the kitchen is busy.",
    pain: "The phone rings mid-service, DMs pile up, and group bookings get lost in a notebook.",
    workflows: [
      "Table bookings and changes over WhatsApp and Instagram",
      "Menu, allergen and opening-hours answers from your own information",
      "Group and event enquiries collected and passed to the manager",
      "Review requests and reminders the day after a visit",
    ],
  },
  {
    slug: "car-wash-detailing",
    name: "Car wash & detailing",
    headline: "A booking diary that fills itself and reminds customers to come back.",
    pain: "Quotes depend on vehicle size and package, so every enquiry turns into a back-and-forth.",
    workflows: [
      "Quotes by vehicle type and package, then a confirmed slot",
      "Deposit requests for longer detailing jobs",
      "Day-before reminders to cut no-shows",
      "Rebooking prompts when a ceramic or valet is due again",
    ],
  },
  {
    slug: "firearms-marketplace",
    name: "Firearms marketplace",
    headline: "Listings and enquiries for licensed dealers, with compliance built into the flow.",
    pain: "Regulated sales need the right checks at the right moment, and staff spend their time repeating the same rules.",
    workflows: [
      "Listing management for licensed dealers",
      "Licence and permit requirements explained before contact is shared",
      "Every enquiry held for staff review; nothing is promised automatically",
      "A complete record of who asked what, and when",
    ],
  },
  {
    slug: "e-commerce",
    name: "E-commerce",
    headline: "Pre-sale questions and order updates answered from your real catalogue.",
    pain: "Shoppers ask about sizes, stock and delivery before they buy, and abandon when nobody answers.",
    workflows: [
      "Product questions answered from your live catalogue",
      "Order status and delivery updates without a support ticket",
      "Returns and exchanges started on policy, approved by staff",
      "Back-in-stock and abandoned-basket follow-ups",
    ],
  },
] as const;

export const process = [
  {
    title: "Discover",
    body: "A working session in your business. We map where enquiries come from, what slows the team down and what must never be automated.",
  },
  {
    title: "Design",
    body: "A short written plan: the workflows, the rules the assistant follows, and what success looks like in the first month.",
  },
  {
    title: "Build",
    body: "We connect your channels and data to Onyx Platform and build anything bespoke, a website or an integration, alongside.",
  },
  {
    title: "Run",
    body: "A supervised start where your team approves every reply, then gradual automation as confidence grows. We stay on to tune it.",
  },
] as const;

export const modules = [
  {
    title: "Unified inbox",
    body: "WhatsApp, email and web chat in one queue, with the customer's history beside every thread.",
  },
  {
    title: "Approvals",
    body: "Drafts that need a human wait here, with the checks they passed and the data they used.",
  },
  { title: "Customers & leads", body: "Contacts, notes and pipeline shared across the team." },
  {
    title: "Catalogue & stock",
    body: "Products, vehicles or listings that the assistant reads from and never invents.",
  },
  { title: "Automations", body: "Reminders, follow-ups and hand-offs that run on schedule." },
  { title: "Usage & billing", body: "Clear plans, monthly AI usage and invoices in one place." },
] as const;

export const principles = [
  "Human approval wherever it matters",
  "Each business's data kept separate",
  "Every AI action logged and reviewable",
  "Built and supported in Malta",
] as const;

export const faq = [
  {
    q: "Will the AI send messages without us seeing them?",
    a: "Only if you allow it, and only for low-risk replies you choose, such as opening hours or availability. Prices, finance, complaints and anything the assistant is unsure about always wait for a person.",
  },
  {
    q: "Where does the assistant get its answers?",
    a: "From your own data: your stock, listings, menu, prices and policies. It does not make up products or prices, and it says so when it doesn't know.",
  },
  {
    q: "Do we need to replace our website or tools?",
    a: "No. Onyx connects to what you already use. If your website is holding you back, we can rebuild it, but it isn't a requirement.",
  },
  {
    q: "How long does it take to go live?",
    a: "Most businesses start a supervised pilot within a few weeks of the discovery session. The exact timeline depends on your channels and data.",
  },
  {
    q: "What does it cost?",
    a: "Onyx Platform is a monthly subscription; bespoke work is quoted after discovery. Email us and we'll give you a clear figure for your business.",
  },
] as const;

/** Illustrative approval-queue rows. Fictional; no real customers. */
export const queueMock = [
  { channel: "WhatsApp", text: "Is the blue hatchback still available?", state: "Draft ready" },
  { channel: "Instagram", text: "Table for 6 on Friday at 8?", state: "Booked" },
  { channel: "Email", text: "Can you do a better price on this one?", state: "Needs approval" },
] as const;
