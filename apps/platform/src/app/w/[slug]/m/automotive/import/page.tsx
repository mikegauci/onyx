import { withApi } from "@/lib/api-client";
import { automotivePath } from "@/lib/automotive";
import { formatInZone } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { workspaceWith } from "@/lib/settings-guard";

import { ImportControls, SourceForm } from "./import-forms";

export default async function ImportPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const path = automotivePath(slug, "import");
  const workspace = await workspaceWith(slug, "catalogue.import", path);
  const source = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/automotive/source", { params: { path: { slug } } }),
    ),
    path,
  );

  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="source-heading" className="flex flex-col gap-3">
        <h2 id="source-heading" className="text-lg font-medium">
          Website
        </h2>
        <p className="text-muted-foreground max-w-2xl text-sm">
          Onyx reads your listings from your website. It only reads: nothing on the website changes.
          Each import shows what would change first; cars taken off the website are marked &quot;no
          longer listed&quot;, never deleted.
        </p>
        <SourceForm
          slug={slug}
          baseUrl={source?.base_url ?? ""}
          fieldMap={source ? JSON.stringify(source.field_map, null, 2) : ""}
        />
      </section>
      {source ? (
        <section aria-labelledby="import-heading" className="flex flex-col gap-3">
          <h2 id="import-heading" className="text-lg font-medium">
            Import
          </h2>
          <p className="text-muted-foreground text-sm">
            {source.last_imported_at ? (
              <>
                Last imported{" "}
                <time dateTime={source.last_imported_at}>
                  {formatInZone(source.last_imported_at, workspace.timezone)}
                </time>
                .
              </>
            ) : (
              "Not imported yet."
            )}
          </p>
          <ImportControls slug={slug} />
        </section>
      ) : null}
    </div>
  );
}
