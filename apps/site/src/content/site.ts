/**
 * Copy and settings for the Onyx Studio landing page, kept in one place so the owner can review
 * and change wording without touching layout code. No testimonials, logos or prices are shown
 * until the owner supplies real ones.
 */
export const site = {
  name: "Onyx Studio",
  tagline: "Business operations and AI automation, built around your team.",
  description:
    "Onyx Studio builds websites, automations and AI assistants for growing businesses in Malta, and runs Onyx Platform: one place for enquiries, customers, stock and approvals.",
  contactEmail: "info@onyx.mt",
  location: "Malta",
} as const;

export const nav = [
  { label: "Services", href: "#services" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Platform", href: "#platform" },
  { label: "Contact", href: "#contact" },
] as const;

export const services = [
  {
    title: "Websites",
    body: "Fast, accessible websites on modern hosting, connected to your stock and your enquiries instead of sitting apart from them.",
  },
  {
    title: "Automation",
    body: "We map the repetitive steps in your day (follow-ups, reminders, copying data between tools) and hand them to reliable workflows.",
  },
  {
    title: "AI assistants",
    body: "Assistants that draft replies from your own catalogue and policies. Your staff approve what goes out; nothing risky is sent on its own.",
  },
  {
    title: "Integrations",
    body: "WhatsApp, email, web chat, payments and your existing website, joined up so every enquiry lands in one inbox.",
  },
] as const;

export const steps = [
  { title: "Enquiry", body: "A customer writes on WhatsApp, email or web chat." },
  { title: "AI draft", body: "The assistant checks your stock and policies and drafts a reply." },
  { title: "Staff approval", body: "Your team reviews, edits or approves it in one click." },
  { title: "Order", body: "Reservations, deposits and documents follow the agreed rules." },
  { title: "Fulfilment", body: "Collection, delivery and after-sale reminders are tracked." },
] as const;

export const modules = [
  {
    title: "Unified inbox",
    body: "WhatsApp, email and web chat in one queue, with the full customer history beside each thread.",
    wide: true,
  },
  {
    title: "Approvals",
    body: "Every AI draft that needs a human waits here, with the checks it passed.",
    wide: false,
  },
  {
    title: "Customers",
    body: "Contacts, leads and notes, shared across the team.",
    wide: false,
  },
  {
    title: "Catalogue and stock",
    body: "Products or vehicles, prices and availability that the assistant reads from, never invents.",
    wide: false,
  },
  {
    title: "AI assistant",
    body: "Grounded in your own data, scoped to your business, and able to say “I don’t know”.",
    wide: false,
  },
  {
    title: "Usage and billing",
    body: "Clear plans, AI usage per month, and invoices in one place.",
    wide: true,
  },
] as const;

export const trust = [
  "Human approval wherever it matters",
  "Each business’s data kept separate",
  "Every AI action logged and reviewable",
  "Built and supported in Malta",
] as const;

/** Illustrative approval-queue rows for the hero mock. Fictional; no real customers. */
export const queueMock = [
  {
    channel: "WhatsApp",
    who: "New enquiry",
    text: "Is the blue hatchback still available?",
    state: "Draft ready",
  },
  {
    channel: "Email",
    who: "Returning customer",
    text: "Can I book a viewing on Saturday?",
    state: "Needs approval",
  },
  {
    channel: "Web chat",
    who: "New enquiry",
    text: "Do you offer finance on this model?",
    state: "Escalated",
  },
] as const;
