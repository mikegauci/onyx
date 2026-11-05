import { getApiHealth } from "@/lib/api-health";
import { platformEnv } from "@/lib/env";

import { ApiStatus } from "../../dashboard/api-status";

export default async function AdminStatusPage() {
  const health = await getApiHealth(platformEnv().apiUrl);
  return (
    <>
      <h1 className="text-2xl font-semibold tracking-tight">API status</h1>
      <ApiStatus health={health} />
    </>
  );
}
