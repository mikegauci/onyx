import { PageHeader } from "@onyx/ui/components/page";
import { BookOpen, ClipboardList, Download } from "lucide-react";
import Link from "next/link";

import { getWorkspace } from "@/lib/data";
import { GUIDES } from "@/lib/guides";
import { requireOk } from "@/lib/guards";

type Props = { params: Promise<{ slug: string }> };

const ICONS = { onboarding: BookOpen, operator: ClipboardList };
const FOCUS = "focus-visible:ring-ring focus-visible:ring-2 focus-visible:outline-none";

export default async function HelpPage({ params }: Props) {
  const { slug } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}/help`);
  const base = `/w/${workspace.slug}/help`;
  return (
    <>
      <PageHeader
        eyebrow="Help"
        title="Guides"
        description="How to use Onyx, step by step. Each guide is also a PDF you can print or share with your team."
      />
      <ul className="grid gap-4 md:grid-cols-2">
        {GUIDES.map((guide) => {
          const Icon = ICONS[guide.slug];
          return (
            <li
              key={guide.slug}
              className="bg-card flex flex-col gap-4 rounded-2xl border p-5 sm:p-6"
            >
              <Icon aria-hidden className="text-brand size-5" />
              <div className="flex flex-col gap-1.5">
                <h2 className="text-base font-medium tracking-tight">
                  <Link
                    href={`${base}/${guide.slug}`}
                    className={`${FOCUS} rounded-sm hover:underline`}
                  >
                    {guide.title}
                  </Link>
                </h2>
                <p className="text-muted-foreground text-sm">{guide.summary}</p>
              </div>
              <a
                href={`/guides/onyx-${guide.slug}-guide.pdf`}
                download
                className={`${FOCUS} text-brand mt-auto inline-flex items-center gap-1.5 self-start rounded-sm text-sm font-medium underline-offset-4 hover:underline`}
              >
                <Download aria-hidden className="size-4" />
                Download PDF
                <span className="sr-only"> for {guide.title}</span>
              </a>
            </li>
          );
        })}
      </ul>
      <p className="text-muted-foreground text-sm">
        Something not working? Note the “Reference” code Onyx shows and send it to your Onyx
        contact. Never send customer messages or personal details to support.
      </p>
    </>
  );
}
