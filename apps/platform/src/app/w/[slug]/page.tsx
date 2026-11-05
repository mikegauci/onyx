import { Badge } from "@onyx/ui/components/badge";
import { Card, CardDescription, CardHeader, CardTitle } from "@onyx/ui/components/card";
import { EmptyState } from "@onyx/ui/components/states";
import { Blocks } from "lucide-react";
import Link from "next/link";

import { getWorkspace } from "@/lib/data";
import { requireOk } from "@/lib/guards";
import { moduleLabel } from "@/lib/modules";

type Props = { params: Promise<{ slug: string }> };

export default async function WorkspaceOverviewPage({ params }: Props) {
  const { slug } = await params;
  const workspace = requireOk(await getWorkspace(slug), `/w/${slug}`);

  return (
    <>
      <div className="flex flex-col gap-1">
        <h1 className="text-2xl font-semibold tracking-tight">{workspace.name}</h1>
        <p className="text-muted-foreground text-sm">
          Your role: <Badge variant="secondary">{workspace.role}</Badge> · Timezone{" "}
          {workspace.timezone}
        </p>
      </div>
      <section aria-labelledby="modules-heading" className="flex flex-col gap-3">
        <h2 id="modules-heading" className="font-medium">
          Enabled modules
        </h2>
        {workspace.modules.length === 0 ? (
          <EmptyState
            icon={Blocks}
            title="No modules enabled yet"
            description="An administrator can enable modules for this workspace."
          />
        ) : (
          <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {workspace.modules.map((key) => (
              <li key={key}>
                <Link
                  href={`/w/${workspace.slug}/m/${key}`}
                  className="focus-visible:ring-ring block rounded-xl focus-visible:ring-2 focus-visible:outline-none"
                >
                  <Card className="hover:bg-muted/50 h-full transition-colors">
                    <CardHeader>
                      <CardTitle>{moduleLabel(key)}</CardTitle>
                      <CardDescription>Open {moduleLabel(key)}</CardDescription>
                    </CardHeader>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </section>
    </>
  );
}
