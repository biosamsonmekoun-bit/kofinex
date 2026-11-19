"use client";

import * as React from "react";
import { X } from "lucide-react";

/** Fenêtre modale accessible basée sur l'élément natif <dialog>. */
const WIDTH = { md: "max-w-lg", lg: "max-w-3xl", xl: "max-w-5xl" } as const;

export function Dialog({ open, onClose, title, description, children, size = "md" }: {
  open: boolean; onClose: () => void; title: string; description?: string; children: React.ReactNode; size?: keyof typeof WIDTH;
}) {
  const ref = React.useRef<HTMLDialogElement>(null);

  React.useEffect(() => {
    const el = ref.current;
    if (!el) return;
    if (open && !el.open) el.showModal();
    if (!open && el.open) el.close();
  }, [open]);

  return (
    <dialog ref={ref} onClose={onClose} onCancel={onClose}
            className={`w-[calc(100%-2rem)] ${WIDTH[size]} max-h-[calc(100vh-2rem)] overflow-y-auto rounded-lg border bg-card p-0 text-card-foreground shadow-xl backdrop:bg-sidebar/50 backdrop:backdrop-blur-[1px]`}>
      <div className="flex items-start justify-between border-b px-5 py-4">
        <div>
          <h2 className="text-base font-semibold text-foreground">{title}</h2>
          {description && <p className="mt-1 text-sm text-muted-foreground">{description}</p>}
        </div>
        <button type="button" onClick={onClose} aria-label="Fermer"
                className="rounded p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="px-5 py-4">{open && children}</div>
    </dialog>
  );
}
