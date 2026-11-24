import { getApiHealth } from "@/lib/api-health";
import { platformEnv } from "@/lib/env";

import { ApiStatus } from "../../dashboard/api-status";

export default async function AdminStatusPage() {
  const health = await getApiHealth(platformEnv().apiUrl);
  return (
    <>
      <h1 className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance">
        API status
      </h1>
      <ApiStatus health={health} />
    </>
  );
}
