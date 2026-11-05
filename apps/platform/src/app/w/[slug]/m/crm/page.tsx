import { redirect } from "next/navigation";
import { crmPath } from "@/lib/crm";
export default async function CrmPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(crmPath(slug, "leads"));
}
