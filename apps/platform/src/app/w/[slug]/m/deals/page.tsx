import { redirect } from "next/navigation";

import { dealsPath } from "@/lib/deals";

type Props = { params: Promise<{ slug: string }> };

export default async function DealsIndex({ params }: Props) {
  const { slug } = await params;
  redirect(dealsPath(slug, "board"));
}
