import type * as React from "react";

import { cn } from "../lib/utils";

/** Small mono, uppercase label with an orange rule, as on the onyx.mt site. */
export function Eyebrow({
  className,
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  return (
    <p
      className={cn(
        "text-muted-foreground flex items-center gap-2.5 font-mono text-[11px] tracking-[0.2em] uppercase",
        className,
      )}
    >
      <span aria-hidden className="bg-brand h-px w-6" />
      {children}
    </p>
  );
}

type PageHeaderProps = {
  title: React.ReactNode;
  eyebrow?: React.ReactNode;
  description?: React.ReactNode;
  /** Buttons or links aligned to the right on wide screens. */
  actions?: React.ReactNode;
  /** Section tabs shown under the title. */
  children?: React.ReactNode;
  id?: string;
  className?: string;
};

/** The one `<h1>` on a page: light, tight display type with optional eyebrow, actions and tabs. */
export function PageHeader({
  title,
  eyebrow,
  description,
  actions,
  children,
  id,
  className,
}: PageHeaderProps) {
  return (
    <header className={cn("flex flex-col gap-5", className)}>
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div className="flex min-w-0 flex-col gap-2">
          {eyebrow ? <Eyebrow>{eyebrow}</Eyebrow> : null}
          <h1
            id={id}
            className="text-[clamp(1.6rem,3vw,2.1rem)] leading-tight font-light tracking-[-0.03em] text-balance"
          >
            {title}
          </h1>
          {description ? (
            <p className="text-muted-foreground max-w-2xl text-sm text-pretty">{description}</p>
          ) : null}
        </div>
        {actions ? (
          <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div>
        ) : null}
      </div>
      {children}
    </header>
  );
}

type PanelProps = Omit<React.ComponentProps<"section">, "title"> & {
  title?: React.ReactNode;
  description?: React.ReactNode;
  actions?: React.ReactNode;
  /** Heading level for the title; defaults to h2. */
  as?: "h2" | "h3";
  /** Remove the body padding, e.g. for a flush table or list. */
  flush?: boolean;
};

/** A bordered surface with an optional header row. The building block for page sections. */
export function Panel({
  title,
  description,
  actions,
  as: Heading = "h2",
  flush = false,
  className,
  children,
  ...props
}: PanelProps) {
  return (
    <section className={cn("bg-card rounded-2xl border", className)} {...props}>
      {title || actions ? (
        <div className="flex items-start justify-between gap-3 border-b px-5 py-4">
          <div className="flex min-w-0 flex-col gap-1">
            {title ? <Heading className="text-sm font-medium">{title}</Heading> : null}
            {description ? (
              <p className="text-muted-foreground text-xs text-pretty">{description}</p>
            ) : null}
          </div>
          {actions ? <div className="flex shrink-0 items-center gap-2">{actions}</div> : null}
        </div>
      ) : null}
      <div className={cn(!flush && "p-5")}>{children}</div>
    </section>
  );
}

/** Label/value pairs for record details. */
export function DetailList({
  items,
  className,
}: {
  items: { label: React.ReactNode; value: React.ReactNode }[];
  className?: string;
}) {
  return (
    <dl className={cn("grid gap-x-6 gap-y-4 text-sm sm:grid-cols-2", className)}>
      {items.map((item, i) => (
        <div key={i} className="flex min-w-0 flex-col gap-1">
          <dt className="text-muted-foreground font-mono text-[11px] tracking-[0.12em] uppercase">
            {item.label}
          </dt>
          <dd className="min-w-0 break-words">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}
