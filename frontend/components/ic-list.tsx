"use client";

import { useMemo, useState } from "react";
import { ArrowDown, ArrowUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/form";
import { TH } from "@/components/ui/table";

/** Recherche, tri et pagination côté client d'une liste déjà filtrée par l'API. */
export function useListView<T>(rows: T[] | null | undefined, opts: { text: (r: T) => string; pageSize?: number; sort?: Record<string, (r: T) => string | number | null> }) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<{ key: string; dir: 1 | -1 } | null>(null);
  const size = opts.pageSize ?? 25;
  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase();
    let out = (rows ?? []).filter((r) => !ql || opts.text(r).toLowerCase().includes(ql));
    const fn = sort && opts.sort?.[sort.key];
    if (fn && sort) {
      out = [...out].sort((a, b) => {
        const x = fn(a), y = fn(b);
        if (x === y) return 0;
        if (x === null) return 1;
        if (y === null) return -1;
        return (x < y ? -1 : 1) * sort.dir;
      });
    }
    return out;
  }, [rows, q, sort, opts]);
  const pages = Math.max(1, Math.ceil(filtered.length / size));
  const current = Math.min(page, pages - 1);
  return {
    q, setQ: (v: string) => { setQ(v); setPage(0); }, total: filtered.length, all: filtered,
    rows: filtered.slice(current * size, current * size + size), page: current, pages, setPage,
    sortTh: (key: string, label: string) => (
      <TH aria-sort={sort?.key === key ? (sort.dir === 1 ? "ascending" : "descending") : "none"}>
        <button type="button" className="inline-flex items-center gap-1 hover:text-foreground"
                onClick={() => setSort(sort?.key === key ? { key, dir: sort.dir === 1 ? -1 : 1 } : { key, dir: 1 })}>
          {label}{sort?.key === key && (sort.dir === 1 ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />)}
        </button>
      </TH>
    ),
  };
}

export function SearchBox({ value, onChange, placeholder = "Rechercher…" }: { value: string; onChange: (v: string) => void; placeholder?: string }) {
  return <Input aria-label="Rechercher" className="w-64" placeholder={placeholder} value={value} onChange={(x) => onChange(x.target.value)} />;
}

export function Pager({ page, pages, total, setPage }: { page: number; pages: number; total: number; setPage: (n: number) => void }) {
  if (pages <= 1) return <p className="mt-2 text-xs text-muted-foreground">{total} ligne(s)</p>;
  return (
    <div className="mt-3 flex items-center justify-between text-xs text-muted-foreground">
      <span>{total} ligne(s) · page {page + 1} / {pages}</span>
      <span className="flex gap-2">
        <Button size="sm" variant="outline" disabled={page === 0} onClick={() => setPage(page - 1)}>Précédente</Button>
        <Button size="sm" variant="outline" disabled={page >= pages - 1} onClick={() => setPage(page + 1)}>Suivante</Button>
      </span>
    </div>
  );
}
