import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

import { E2E } from "../playwright.config";

/** Fresh, seeded e2e database for every run (refuses anything but a local *_e2e database). */
export default function globalSetup() {
  execFileSync("uv", ["run", "python", "-m", "app.core.db.e2e_reset", E2E.databaseUrl], {
    cwd: fileURLToPath(new URL("../../api", import.meta.url)),
    stdio: "inherit",
  });
}
