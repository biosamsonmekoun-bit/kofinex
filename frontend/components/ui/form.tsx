import * as React from "react";
import { cn } from "@/lib/utils";

const fieldBase =
  "flex h-9 w-full rounded-md border border-input bg-card px-3 py-1 text-sm text-foreground shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:border-ring focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/30 aria-[invalid=true]:border-destructive disabled:cursor-not-allowed disabled:bg-muted disabled:opacity-60";

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => <input ref={ref} className={cn(fieldBase, className)} {...props} />,
);
Input.displayName = "Input";

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, children, ...props }, ref) => (
    <select ref={ref} className={cn(fieldBase, "pr-8", className)} {...props}>{children}</select>
  ),
);
Select.displayName = "Select";

export function Label({ className, ...props }: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return <label className={cn("text-sm font-medium leading-none", className)} {...props} />;
}

export function Field({ label, htmlFor, hint, required, children }: {
  label: string; htmlFor: string; hint?: string; required?: boolean; children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <Label htmlFor={htmlFor}>
        {label}{required && <span className="text-destructive"> *</span>}
      </Label>
      {children}
      {hint && <p className="text-xs text-muted-foreground">{hint}</p>}
    </div>
  );
}
