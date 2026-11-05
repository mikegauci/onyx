import { redirect } from "next/navigation";
import { cataloguePath } from "@/lib/catalogue";

export default async function CataloguePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  redirect(cataloguePath(slug, "products"));
}
