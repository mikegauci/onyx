import { redirect } from "next/navigation";

/**
 * app.onyx.mt has no landing page of its own; onyx.mt does the selling. Signed-in users land
 * on their workspaces, and the proxy sends everyone else to /login first.
 */
export default function PlatformHomePage() {
  redirect("/workspaces");
}
