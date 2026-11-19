import * as React from "react";
import { cn } from "@/lib/utils";

export function Table({ className, ...props }: React.TableHTMLAttributes<HTMLTableElement>) {
  return (
    <div className="w-full overflow-x-auto rounded-lg border bg-card shadow-card">
      <table className={cn("w-full caption-bottom text-sm tabular-nums", className)} {...props} />
    </div>
  );
}
export const THead = (p: React.HTMLAttributes<HTMLTableSectionElement>) =>
  <thead className="border-b bg-muted/70 text-left text-[11px] font-semibold uppercase tracking-wider text-muted-foreground" {...p} />;
export const TBody = (p: React.HTMLAttributes<HTMLTableSectionElement>) => <tbody className="divide-y" {...p} />;
export const TR = ({ className, ...p }: React.HTMLAttributes<HTMLTableRowElement>) =>
  <tr className={cn("transition-colors hover:bg-muted/50", className)} {...p} />;
export const TH = ({ className, ...p }: React.ThHTMLAttributes<HTMLTableCellElement>) =>
  <th className={cn("px-4 py-2.5 font-semibold", className)} {...p} />;
export const TD = ({ className, ...p }: React.TdHTMLAttributes<HTMLTableCellElement>) =>
  <td className={cn("px-4 py-3 align-middle", className)} {...p} />;
