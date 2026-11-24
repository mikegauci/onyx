/*
 * Classes for native form controls (select, textarea) so they match the shared `Input`.
 * Native elements keep their built-in keyboard and mobile behaviour.
 */
const base =
  "border-input bg-background dark:bg-foreground/[0.03] w-full rounded-lg border text-sm transition-[color,box-shadow,border-color] outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:opacity-50 aria-invalid:border-destructive";

export const selectClass = `${base} h-9 px-3`;
export const textareaClass = `${base} min-h-24 px-3 py-2 placeholder:text-muted-foreground/80`;
