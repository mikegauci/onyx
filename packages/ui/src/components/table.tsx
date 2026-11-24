"use client";

import * as React from "react";
import { cn } from "../lib/utils";

/**
 * `stack` turns each row into a card on phones (below 640px). Give cells a `data-label`
 * (the column name) so stacked values keep their label. Explicit roles keep the table
 * semantics when the layout changes.
 */
function Table({
  className,
  stack = false,
  ...props
}: React.ComponentProps<"table"> & { stack?: boolean }) {
  return (
    <div
      data-slot="table-container"
      data-stack={stack ? "" : undefined}
      className="bg-card relative w-full overflow-x-auto rounded-2xl border [.bg-card_&]:rounded-xl [.bg-card_&]:bg-transparent"
    >
      <table
        role="table"
        data-slot="table"
        className={cn("w-full caption-bottom text-sm", className)}
        {...props}
      />
    </div>
  );
}

function TableHeader({ className, ...props }: React.ComponentProps<"thead">) {
  return (
    <thead
      role="rowgroup"
      data-slot="table-header"
      className={cn("[&_tr]:border-b", className)}
      {...props}
    />
  );
}

function TableBody({ className, ...props }: React.ComponentProps<"tbody">) {
  return (
    <tbody
      role="rowgroup"
      data-slot="table-body"
      className={cn("[&_tr:last-child]:border-0", className)}
      {...props}
    />
  );
}

function TableFooter({ className, ...props }: React.ComponentProps<"tfoot">) {
  return (
    <tfoot
      data-slot="table-footer"
      className={cn("bg-muted/50 border-t font-medium [&>tr]:last:border-b-0", className)}
      {...props}
    />
  );
}

function TableRow({ className, ...props }: React.ComponentProps<"tr">) {
  return (
    <tr
      role="row"
      data-slot="table-row"
      className={cn(
        "hover:bg-foreground/[0.03] has-aria-expanded:bg-foreground/[0.03] data-[state=selected]:bg-muted border-b transition-colors",
        className,
      )}
      {...props}
    />
  );
}

function TableHead({ className, ...props }: React.ComponentProps<"th">) {
  return (
    <th
      role="columnheader"
      data-slot="table-head"
      className={cn(
        "text-muted-foreground h-10 px-3 text-left align-middle font-mono text-[11px] font-normal tracking-[0.12em] whitespace-nowrap uppercase [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className,
      )}
      {...props}
    />
  );
}

function TableCell({ className, ...props }: React.ComponentProps<"td">) {
  return (
    <td
      role="cell"
      data-slot="table-cell"
      className={cn(
        "px-3 py-3 align-middle whitespace-nowrap [&:has([role=checkbox])]:pr-0 [&>[role=checkbox]]:translate-y-[2px]",
        className,
      )}
      {...props}
    />
  );
}

function TableCaption({ className, ...props }: React.ComponentProps<"caption">) {
  return (
    <caption
      data-slot="table-caption"
      className={cn("text-muted-foreground mt-4 text-sm", className)}
      {...props}
    />
  );
}

export { Table, TableHeader, TableBody, TableFooter, TableHead, TableRow, TableCell, TableCaption };
