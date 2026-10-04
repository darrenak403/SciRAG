"use client";

import { ListFilter, Search } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";

export const SORTS = {
  added: { label: "Recently added", sort: "added", order: "desc" },
  year: { label: "Year", sort: "year", order: "desc" },
  title: { label: "Title", sort: "title", order: "asc" },
  author: { label: "Author", sort: "author", order: "asc" },
} as const;

// "Processing" covers a paper that is waiting as well as one being worked on.
export const STATUS_FILTERS = {
  all: { label: "Any status", statuses: [] },
  ready: { label: "Ready", statuses: ["READY"] },
  processing: { label: "Processing", statuses: ["UPLOADED", "PROCESSING"] },
  failed: { label: "Needs attention", statuses: ["FAILED"] },
} as const;

export type LibraryQuery = {
  q: string;
  status: keyof typeof STATUS_FILTERS;
  year: string;
  author: string;
  sort: keyof typeof SORTS;
};

export const EMPTY_QUERY: LibraryQuery = { q: "", status: "all", year: "", author: "", sort: "added" };

export function LibraryToolbar({
  query,
  onChange,
}: {
  query: LibraryQuery;
  onChange: (changes: Partial<LibraryQuery>) => void;
}) {
  const filters = [query.status !== "all", query.year !== "", query.author !== ""].filter(Boolean).length;

  return (
    <div className="flex flex-wrap items-center gap-2">
      <div className="relative min-w-48 flex-1">
        <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
        <Input
          type="search"
          value={query.q}
          onChange={(event) => onChange({ q: event.target.value })}
          placeholder="Search papers…"
          aria-label="Search papers by title"
          className="pl-8"
        />
      </div>

      <Popover>
        <PopoverTrigger render={<Button variant="outline" />}>
          <ListFilter />
          Filter
          {filters > 0 && <span className="text-muted-foreground tabular-nums">· {filters}</span>}
        </PopoverTrigger>
        <PopoverContent align="end" className="flex w-64 flex-col gap-3">
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-status">Status</Label>
            <NativeSelect
              id="filter-status"
              value={query.status}
              onChange={(event) => onChange({ status: event.target.value as LibraryQuery["status"] })}
            >
              {Object.entries(STATUS_FILTERS).map(([value, { label }]) => (
                <option key={value} value={value}>
                  {label}
                </option>
              ))}
            </NativeSelect>
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-year">Year</Label>
            <Input
              id="filter-year"
              type="number"
              min={1000}
              max={2100}
              value={query.year}
              onChange={(event) => onChange({ year: event.target.value })}
              placeholder="Any year"
            />
          </div>
          <div className="flex flex-col gap-1.5">
            <Label htmlFor="filter-author">Author</Label>
            <Input
              id="filter-author"
              value={query.author}
              onChange={(event) => onChange({ author: event.target.value })}
              placeholder="Any author"
            />
          </div>
          {filters > 0 && (
            <Button variant="ghost" size="sm" onClick={() => onChange({ status: "all", year: "", author: "" })}>
              Clear filters
            </Button>
          )}
        </PopoverContent>
      </Popover>

      <NativeSelect
        aria-label="Sort by"
        value={query.sort}
        onChange={(event) => onChange({ sort: event.target.value as LibraryQuery["sort"] })}
      >
        {Object.entries(SORTS).map(([value, { label }]) => (
          <option key={value} value={value}>
            {label}
          </option>
        ))}
      </NativeSelect>
    </div>
  );
}
