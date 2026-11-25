"use client";

import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { site } from "@/content/site";
import { webDesignPhone } from "@/content/web-design";

import { isWebsiteDesignCampaign, websiteDesignCampaign } from "./campaign";

const phone = webDesignPhone.international;
const whatsApp = `https://wa.me/${phone.slice(1)}`;
const contacts = [
  { label: "Email us", hint: site.contactEmail, href: `mailto:${site.contactEmail}` },
  { label: "Call us", hint: webDesignPhone.display, href: `tel:${phone}` },
  { label: "Text us", hint: "SMS", href: `sms:${phone}` },
];

function ContactLinks({ whatsAppHref }: { whatsAppHref: string }) {
  return (
    <ul className="mt-6 grid gap-3 min-[380px]:grid-cols-2">
      {[...contacts, { label: "WhatsApp", hint: "Send a message", href: whatsAppHref }].map(
        ({ label, hint, href }) => (
          <li key={label} className="min-w-0">
            <a
              href={href}
              className="hover:border-brand/60 focus-visible:ring-ring/60 block rounded-xl border border-white/10 px-4 py-3 transition-colors focus-visible:ring-2 focus-visible:outline-none"
            >
              <span className="block text-sm font-medium">{label}</span>
              <span className="text-muted-foreground block text-sm break-words">{hint}</span>
            </a>
          </li>
        ),
      )}
    </ul>
  );
}

function TaggedContactLinks() {
  const isCampaign = isWebsiteDesignCampaign(useSearchParams());
  const href = isCampaign
    ? `${whatsApp}?text=${encodeURIComponent(websiteDesignCampaign.message)}`
    : whatsApp;
  return <ContactLinks whatsAppHref={href} />;
}

export function EnquiryContacts() {
  return (
    <Suspense fallback={<ContactLinks whatsAppHref={whatsApp} />}>
      <TaggedContactLinks />
    </Suspense>
  );
}

function CampaignField() {
  const isCampaign = isWebsiteDesignCampaign(useSearchParams());
  return isCampaign ? (
    <input type="hidden" name="campaign" value={websiteDesignCampaign.code} />
  ) : null;
}

export function EnquiryCampaignField() {
  return (
    <Suspense fallback={null}>
      <CampaignField />
    </Suspense>
  );
}
