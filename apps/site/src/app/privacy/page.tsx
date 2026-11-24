import type { Metadata } from "next";
import Link from "next/link";
import type { ReactNode } from "react";

import { site } from "@/content/site";

export const metadata: Metadata = {
  title: "Privacy policy",
  description: `How ${site.name} and Onyx Platform handle personal data.`,
  alternates: { canonical: "/privacy" },
};

const UPDATED = "24 November 2026";

const PROVIDERS: { name: string; purpose: string; where: string }[] = [
  { name: "Supabase", purpose: "Database, sign-in and file storage", where: "EU (Frankfurt)" },
  { name: "Render", purpose: "Runs the Onyx API", where: "EU (Frankfurt)" },
  {
    name: "Vercel",
    purpose: "Hosts this website and the Onyx Platform web app",
    where: "EU and US",
  },
  {
    name: "Meta (WhatsApp Business Platform)",
    purpose: "Receives and sends WhatsApp messages for businesses that connect WhatsApp",
    where: "EU and US",
  },
  {
    name: "OpenAI",
    purpose: "Drafts replies and searches documents when a business uses the AI assistant",
    where: "US",
  },
  { name: "Resend", purpose: "Sends sign-in links and email replies", where: "EU and US" },
  {
    name: "Stripe",
    purpose: "Subscription billing for our business customers",
    where: "EU and US",
  },
  { name: "Sentry", purpose: "Error monitoring", where: "EU" },
];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-3">
      <h2 className="text-xl font-light tracking-tight">{title}</h2>
      <div className="text-muted-foreground [&_strong]:text-foreground flex flex-col gap-3 text-[15px] leading-relaxed [&_ul]:list-disc [&_ul]:space-y-1.5 [&_ul]:pl-5">
        {children}
      </div>
    </section>
  );
}

export default function PrivacyPage() {
  const email = (
    <a
      className="text-brand underline-offset-4 hover:underline"
      href={`mailto:${site.contactEmail}`}
    >
      {site.contactEmail}
    </a>
  );
  return (
    <main className="mx-auto flex max-w-3xl flex-col gap-12 px-6 py-16 sm:py-24">
      <Link
        href="/"
        className="text-muted-foreground hover:text-foreground flex items-center gap-2 self-start text-sm"
      >
        <span aria-hidden className="bg-brand size-2 rounded-full" />
        {site.name}
      </Link>

      <header className="flex flex-col gap-4">
        <p className="text-muted-foreground flex items-center gap-3 font-mono text-xs tracking-[0.2em] uppercase">
          <span aria-hidden className="bg-brand h-px w-8" />
          Legal
        </p>
        <h1 className="text-[clamp(2.2rem,5vw,3.4rem)] leading-[1.05] font-light tracking-[-0.03em]">
          Privacy policy
        </h1>
        <p className="text-muted-foreground text-sm">Last updated {UPDATED}</p>
      </header>

      <Section title="Who we are">
        <p>
          {site.name} is the trading name of <strong>{site.legal.name}</strong>,{" "}
          {site.legal.address.join(", ")} (VAT {site.legal.vat}). This policy covers this website
          (onyx.mt) and Onyx Platform (app.onyx.mt), the software we provide to businesses. Contact
          us about privacy at {email}.
        </p>
      </Section>

      <Section title="Our role">
        <ul>
          <li>
            <strong>For our own customers and visitors</strong> (people who contact us, sign in or
            pay for a subscription) we are the data controller.
          </li>
          <li>
            <strong>For the businesses that use Onyx Platform</strong>, we process their customers’
            messages and records on their behalf, as a data processor. The business is the
            controller and decides why the data is used. If you have messaged a business that uses
            Onyx, contact that business first; we will help them answer your request.
          </li>
        </ul>
      </Section>

      <Section title="What we process">
        <ul>
          <li>
            <strong>Account data:</strong> name, work email and role of the staff who use Onyx
            Platform, and sign-in records.
          </li>
          <li>
            <strong>Business data:</strong> the conversations, contacts, leads, products, quotes and
            documents a business keeps in Onyx Platform. This includes messages its customers send
            by WhatsApp or email, and their names, phone numbers and email addresses.
          </li>
          <li>
            <strong>AI data:</strong> when a business uses the AI assistant, the relevant
            conversation and catalogue data is sent to the AI provider to draft a reply. Drafts are
            reviewed by staff, and we record which tools the assistant used, but not full message
            text in our logs.
          </li>
          <li>
            <strong>Billing data:</strong> the business’s plan and invoices. Card details are
            handled by Stripe and never reach us.
          </li>
          <li>
            <strong>Technical data:</strong> error reports and service logs used to keep the service
            secure and working.
          </li>
        </ul>
      </Section>

      <Section title="How we use it">
        <ul>
          <li>
            To provide Onyx Platform: receive, show, draft and send messages, and keep records.
          </li>
          <li>To sign people in, secure accounts and prevent abuse.</li>
          <li>To bill our business customers.</li>
          <li>To answer enquiries sent to us.</li>
        </ul>
        <p>
          The legal bases are the contract with our customer, our legitimate interest in running a
          secure service, and legal obligations such as keeping tax records. We do not sell personal
          data, use it for advertising, or use it to train AI models.
        </p>
      </Section>

      <Section title="WhatsApp">
        <p>
          When a business connects its WhatsApp number, messages to and from that number pass
          through Meta’s WhatsApp Business Platform and are stored in that business’s Onyx
          workspace. We use them only to provide the service to that business. Each business’s data
          is kept separate from every other business’s.
        </p>
      </Section>

      <Section title="Service providers">
        <p>
          We use these providers to run the service. Each processes data only on our instructions.
        </p>
        <div className="overflow-x-auto rounded-2xl border border-white/10">
          <table className="w-full text-left text-sm">
            <thead className="font-mono text-[11px] tracking-[0.12em] uppercase">
              <tr className="border-b border-white/10">
                <th className="px-4 py-3 font-normal">Provider</th>
                <th className="px-4 py-3 font-normal">Purpose</th>
                <th className="px-4 py-3 font-normal">Location</th>
              </tr>
            </thead>
            <tbody>
              {PROVIDERS.map((p) => (
                <tr key={p.name} className="border-b border-white/10 last:border-0">
                  <td className="text-foreground px-4 py-3 align-top">{p.name}</td>
                  <td className="px-4 py-3 align-top">{p.purpose}</td>
                  <td className="px-4 py-3 align-top whitespace-nowrap">{p.where}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p>
          Transfers outside the EU rely on the European Commission’s adequacy decisions, including
          the EU–US Data Privacy Framework, or its Standard Contractual Clauses.
        </p>
      </Section>

      <Section title="How long we keep it">
        <p>
          Account and business data are kept while the business’s subscription is active. When it
          ends, we delete or return the business’s data as agreed in its contract. Billing records
          are kept as long as tax law requires.
        </p>
      </Section>

      <Section title="Your rights and deleting your data">
        <p>
          You can ask to access, correct or delete your personal data, to restrict or object to its
          use, or to receive a copy. To ask, email {email} with the phone number or email address
          you used. If the data belongs to a business that uses Onyx, we will pass your request to
          that business and help it respond. We reply within one month.
        </p>
        <p>
          If you are unhappy with how we handle your data, you can complain to the Information and
          Data Protection Commissioner in Malta (idpc.org.mt).
        </p>
      </Section>

      <Section title="Cookies">
        <p>
          This website sets no cookies and runs no analytics. Onyx Platform uses only the cookies
          needed to keep you signed in.
        </p>
      </Section>

      <Section title="Changes">
        <p>We will update this page if how we handle data changes, and change the date above.</p>
      </Section>
    </main>
  );
}
