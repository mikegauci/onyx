import { servicePath } from "./service-links";
import { webDesignPath } from "./web-design";

/**
 * Copy and settings for the Onyx Studio landing page, kept in one place so the owner can review
 * and change wording without touching layout code. No testimonials, client logos, prices or
 * invented statistics are shown until the owner supplies real ones.
 */
export const site = {
  name: "Onyx Studio",
  tagline: "AI that answers, books and follows up. People who stay in charge.",
  description:
    "Onyx Studio builds websites, apps, brands and AI automation for businesses in Malta and Gozo, and helps them get found through SEO.",
  contactEmail: "info@onyx.mt",
  location: "Malta",
  /** The registered business details, as on official documents (Meta business verification). */
  legal: {
    name: "Michael Gauci",
    address: [
      "Villa Lugano, No 1",
      "Triq Dawret in-Nawfragju",
      "Xemxija, St. Paul's Bay SPB 4801",
      "Malta",
    ],
    vat: "MT26707111",
  },
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
  lines: ["Intelligence", "that works the"],
  /** Rotates in the last line of the headline; the first is what search engines and no-JS see. */
  rotating: [
    "front desk.",
    "showroom.",
    "reservations.",
    "client inbox.",
    "listings.",
    "checkout.",
    "diary.",
    "intake desk.",
  ],
  body: "We connect your WhatsApp, inbox, website and stock to one AI-assisted workspace, so every enquiry gets a fast, accurate answer, and your team only steps in where it matters.",
  primary: "Start a project",
  secondary: "See the system",
} as const;

/** Read word by word as the visitor scrolls. */
export const statement =
  "Most businesses don't need more software. They need the enquiries, bookings and follow-ups they already have to stop slipping through the cracks. We build websites and automations that make those everyday tasks easier.";

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
    body: "Assistants that handle routine WhatsApp, email and web chat enquiries using your approved information.",
    tags: ["Enquiry replies", "Lead qualification", "Booking"],
    href: `${servicePath("ai-automation")}#ai-assistants`,
    linkLabel: "Explore AI assistants",
  },
  {
    title: "Workflow automation",
    body: "Give follow-ups, reminders, document requests and hand-offs a clear next step.",
    tags: ["Reminders", "Follow-ups", "Hand-offs"],
    href: `${servicePath("ai-automation")}#workflow-automation`,
    linkLabel: "Explore workflow automation",
  },
  {
    title: "Websites that sell",
    body: "Business websites and online shops, with options for bookings, stock and a tailored CMS.",
    tags: ["Web design", "Development", "Tailored CMS"],
    href: webDesignPath,
    linkLabel: "Explore web design and development",
  },
  {
    title: "Integrations",
    body: "Connect payments, calendars, stock and inboxes as part of your build or automation.",
    tags: ["WhatsApp Business", "Stripe", "Booking tools"],
    href: `${servicePath("ai-automation")}#integrations`,
    linkLabel: "See integrations in an automation project",
  },
  {
    title: "App development",
    body: "iOS and Android apps, web apps and portals built around what customers and teams need to do.",
    tags: ["iOS and Android", "Web apps", "Portals"],
    href: servicePath("app-development"),
    linkLabel: "Explore app development",
  },
  {
    title: "Branding and graphic design",
    body: "Brand identity, logos and graphics for the places people meet your business online and in print.",
    tags: ["Brand identity", "Social graphics", "Print design"],
    href: servicePath("branding-graphic-design"),
    linkLabel: "Explore branding and graphic design",
  },
  {
    title: "SEO",
    body: "Local SEO for Malta and Gozo, technical audits and ongoing work to improve search visibility.",
    tags: ["Local SEO", "Technical audits", "Ongoing SEO"],
    href: servicePath("seo"),
    linkLabel: "Explore SEO",
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
      "Availability, mileage and spec answers from your live stock",
      "Viewings and test drives booked into the calendar",
      "Finance and trade-in questions routed to a salesperson",
      "Sold-car alerts and follow-ups for buyers who missed out",
    ],
  },
  {
    slug: "restaurants-hospitality",
    name: "Restaurants & hospitality",
    headline: "Bookings, questions and events handled while the kitchen is busy.",
    pain: "The phone rings mid-service, DMs pile up, and group bookings get lost in a notebook.",
    workflows: [
      "Table bookings and changes over WhatsApp and Instagram",
      "Menu, allergen and opening-hours answers from your own information",
      "Group, event and private-dining enquiries passed to the manager",
      "Review requests and reminders after a visit",
    ],
  },
  {
    slug: "accounting-firms",
    name: "Accounting firms",
    headline: "Fewer chasers, cleaner inboxes, every deadline on record.",
    pain: "Partners spend their week chasing the same documents from the same clients, by email and by phone.",
    workflows: [
      "Document requests and reminders until every file is in",
      "New-client intake and engagement details collected up front",
      "Routine questions on deadlines and fees answered from your policies",
      "Anything advisory flagged for an accountant before a reply",
    ],
  },
  {
    slug: "hr-recruitment",
    name: "HR & recruitment",
    headline: "Candidates screened, scheduled and kept warm without the admin.",
    pain: "Good candidates drop out while CVs sit unanswered and interview slots go back and forth.",
    workflows: [
      "Applications acknowledged and screened against your criteria",
      "Interviews scheduled around the hiring team's calendars",
      "Status updates so no candidate is left waiting",
      "Onboarding checklists and document collection after an offer",
    ],
  },
  {
    slug: "property-agencies",
    name: "Property agencies",
    headline: "From portal enquiry to booked viewing without the phone tag.",
    pain: "Leads arrive from portals, socials and the website at all hours, and most go cold before an agent replies.",
    workflows: [
      "Buyers and tenants qualified on budget, area and timing",
      "Enquiries matched to listings, with alternatives suggested",
      "Viewings booked around agent availability",
      "Document chasing and landlord updates",
    ],
  },
  {
    slug: "marketplaces",
    name: "Marketplaces",
    headline: "Buyers and sellers answered at scale, with the right checks in the flow.",
    pain: "Listing questions, seller onboarding and disputes all land in one inbox, and regulated categories need extra care.",
    workflows: [
      "Listing questions answered from the listing itself",
      "Seller onboarding and verification steps tracked",
      "Licence or eligibility checks for regulated categories before contact is shared",
      "Disputes and anything sensitive held for staff review",
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
  {
    slug: "clinics-salons-studios",
    name: "Clinics, salons & studios",
    headline: "A diary that fills itself and reminds people to come back.",
    pain: "Appointments are booked by phone between clients, and no-shows leave expensive gaps.",
    workflows: [
      "Appointments booked, moved and confirmed over chat",
      "Day-before reminders and deposits to cut no-shows",
      "Treatment, class and price questions answered from your menu",
      "Rebooking prompts when a client is due again",
    ],
  },
  {
    slug: "legal-professional",
    name: "Legal & professional services",
    headline: "Client intake handled properly, before anyone bills an hour.",
    pain: "Enquiries need the same facts gathered every time, and conflicts or urgency must be spotted early.",
    workflows: [
      "Structured intake that gathers the facts before the first call",
      "Consultations scheduled with the right person",
      "Document requests and signature reminders",
      "Nothing that reads as advice is sent without a professional's approval",
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
