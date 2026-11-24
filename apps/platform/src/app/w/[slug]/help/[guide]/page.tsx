import { PageHeader } from "@onyx/ui/components/page";
import { Download } from "lucide-react";
import { notFound } from "next/navigation";

import { BackLink } from "@/components/back-link";
import { GuideView } from "@/components/guide-view";
import { getWorkspace } from "@/lib/data";
import { guideBySlug } from "@/lib/guides";
import { requireOk } from "@/lib/guards";

type Props = { params: Promise<{ slug: string; guide: string }> };

export default async function GuidePage({ params }: Props) {
  const { slug, guide: guideSlug } = await params;
  const guide = guideBySlug(guideSlug);
  if (!guide) notFound();
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}/help/${guideSlug}`);
  return (
    <>
      <BackLink href={`/w/${workspace.slug}/help`}>All guides</BackLink>
      <PageHeader
        eyebrow="Help"
        title={guide.title}
        description={guide.summary}
        actions={
          <a
            href={`/guides/onyx-${guide.slug}-guide.pdf`}
            download
            className="border-foreground/15 hover:bg-foreground/[0.05] focus-visible:ring-ring inline-flex h-9 items-center gap-2 rounded-full border px-4 text-sm font-medium focus-visible:ring-2 focus-visible:outline-none"
          >
            <Download aria-hidden className="size-4" />
            Download PDF
          </a>
        }
      />
      <GuideView guide={guide} />
    </>
  );
}
