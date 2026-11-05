import { withApi } from "@/lib/api-client";
import { crmPath, type SubjectType } from "@/lib/crm";
import { requireOk } from "@/lib/guards";
import { ActivityList } from "./activity";
import { NoteForm } from "./forms";
import { Pager } from "./list-controls";
export async function ActivitySection({
  slug,
  subjectType,
  id,
  timezone,
  canWrite,
  cursor,
}: {
  slug: string;
  subjectType: SubjectType;
  id: string;
  timezone: string;
  canWrite: boolean;
  cursor?: string;
}) {
  const path = crmPath(slug, `${subjectType}s`, id);
  const page = requireOk(
    await withApi((api) =>
      api.GET("/v1/w/{slug}/crm/activities", {
        params: { path: { slug }, query: { subject_type: subjectType, subject_id: id, cursor } },
      }),
    ),
    path,
  );
  return (
    <section className="flex max-w-2xl flex-col gap-4" aria-labelledby="activity-heading">
      <h3 id="activity-heading" className="font-medium">
        Activity
      </h3>
      {canWrite ? <NoteForm slug={slug} subjectType={subjectType} subjectId={id} /> : null}
      <ActivityList items={page.items} timezone={timezone} />
      <Pager base={path} params={{}} cursor={cursor} nextCursor={page.next_cursor} />
    </section>
  );
}
