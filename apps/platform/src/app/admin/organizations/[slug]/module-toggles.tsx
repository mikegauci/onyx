"use client";

import type { components } from "@onyx/api-client";
import { Button } from "@onyx/ui/components/button";
import { useActionState } from "react";

import { EnabledBadge } from "../../../w/[slug]/settings/modules/modules-table";
import { type ToggleState, setModule } from "./actions";

type Module = components["schemas"]["ModuleOut"];

function ModuleRow({ slug, module }: { slug: string; module: Module }) {
  const [state, action, pending] = useActionState<ToggleState>(
    () => setModule(slug, module.key, !module.enabled),
    { status: "idle" },
  );
  return (
    <li className="flex flex-col gap-2 rounded-md border p-4 sm:flex-row sm:items-center">
      <div className="flex flex-1 flex-col gap-1">
        <span className="font-medium">
          {module.name} <EnabledBadge enabled={module.enabled} />
        </span>
        <span className="text-muted-foreground text-sm">
          {module.requires.length ? `Requires ${module.requires.join(", ")}` : "No requirements"}
        </span>
        {state.status === "error" ? (
          <span role="alert" className="text-destructive text-sm">
            {state.message}
          </span>
        ) : null}
      </div>
      <form action={action}>
        <Button
          type="submit"
          size="sm"
          variant={module.enabled ? "outline" : "default"}
          disabled={pending}
          aria-label={`${module.enabled ? "Disable" : "Enable"} ${module.name}`}
        >
          {pending ? "Saving…" : module.enabled ? "Disable" : "Enable"}
        </Button>
      </form>
    </li>
  );
}

export function ModuleToggles({ slug, modules }: { slug: string; modules: Module[] }) {
  return (
    <ul className="flex flex-col gap-2">
      {modules.map((m) => (
        <ModuleRow key={`${m.key}-${m.enabled}`} slug={slug} module={m} />
      ))}
    </ul>
  );
}
