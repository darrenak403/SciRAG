"use client";

import { type ColumnDef, flexRender, getCoreRowModel, useReactTable } from "@tanstack/react-table";
import { MoreHorizontal } from "lucide-react";
import Link from "next/link";
import { useMemo } from "react";

import { PaperStatusBadge } from "@/components/library/paper-status-badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { authorLine } from "@/lib/format";
import { failureOf } from "@/lib/paper-status";
import type { Paper } from "@/lib/types";

export type PaperAction = "ask" | "edit" | "collect" | "retry" | "delete";

export function PaperTable({
  papers,
  onAction,
}: {
  papers: Paper[];
  onAction: (action: PaperAction, paper: Paper) => void;
}) {
  const columns = useMemo<ColumnDef<Paper>[]>(
    () => [
      {
        id: "title",
        header: "Title",
        cell: ({ row: { original: paper } }) => (
          <Link href={`/library/${paper.id}`} className="line-clamp-2 font-medium whitespace-normal hover:underline">
            {paper.title}
          </Link>
        ),
      },
      {
        id: "authors",
        header: "Authors",
        meta: { className: "hidden md:table-cell" },
        cell: ({ row: { original: paper } }) => (
          <span className="text-muted-foreground" title={paper.authors.join(", ")}>
            {authorLine(paper.authors) || "—"}
          </span>
        ),
      },
      {
        id: "year",
        header: "Year",
        meta: { className: "hidden sm:table-cell" },
        cell: ({ row: { original: paper } }) => (
          <span className="text-muted-foreground tabular-nums">{paper.year ?? "—"}</span>
        ),
      },
      {
        id: "status",
        header: "Status",
        cell: ({ row: { original: paper } }) => (
          <div>
            <PaperStatusBadge paper={paper} />
            {paper.status === "FAILED" && (
              <p className="text-xs text-muted-foreground">{failureOf(paper).title}</p>
            )}
            {paper.needs_reindex && (
              <p className="text-xs text-muted-foreground">Not searchable until it is prepared again</p>
            )}
          </div>
        ),
      },
      {
        id: "actions",
        header: () => <span className="sr-only">Actions</span>,
        cell: ({ row: { original: paper } }) => (
          <DropdownMenu>
            <DropdownMenuTrigger
              render={<Button variant="ghost" size="icon-sm" aria-label={`Actions for ${paper.title}`} />}
            >
              <MoreHorizontal />
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="min-w-44">
              {paper.status === "READY" && (
                <DropdownMenuItem onClick={() => onAction("ask", paper)}>Ask this paper</DropdownMenuItem>
              )}
              <DropdownMenuItem onClick={() => onAction("edit", paper)}>Edit information</DropdownMenuItem>
              <DropdownMenuItem onClick={() => onAction("collect", paper)}>Add to collection</DropdownMenuItem>
              {paper.status === "FAILED" && (
                <DropdownMenuItem onClick={() => onAction("retry", paper)}>Retry processing</DropdownMenuItem>
              )}
              {/* For a paper the queue never took. One that is really waiting is refused by the server. */}
              {paper.status === "UPLOADED" && (
                <DropdownMenuItem onClick={() => onAction("retry", paper)}>Restart processing</DropdownMenuItem>
              )}
              <DropdownMenuSeparator />
              <DropdownMenuItem variant="destructive" onClick={() => onAction("delete", paper)}>
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        ),
      },
    ],
    [onAction],
  );

  // Searching, filtering, sorting and paging all happen on the server; the table only lays rows out.
  const table = useReactTable({
    data: papers,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (paper) => paper.id,
    manualSorting: true,
    manualFiltering: true,
    manualPagination: true,
  });

  const className = (meta: unknown) => (meta as { className?: string } | undefined)?.className;

  return (
    <Table>
      <TableHeader>
        {table.getHeaderGroups().map((group) => (
          <TableRow key={group.id}>
            {group.headers.map((header) => (
              <TableHead key={header.id} className={className(header.column.columnDef.meta)}>
                {flexRender(header.column.columnDef.header, header.getContext())}
              </TableHead>
            ))}
          </TableRow>
        ))}
      </TableHeader>
      <TableBody>
        {table.getRowModel().rows.map((row) => (
          <TableRow key={row.id}>
            {row.getVisibleCells().map((cell) => (
              <TableCell
                key={cell.id}
                className={className(cell.column.columnDef.meta)}
                style={cell.column.id === "actions" ? { width: "2.5rem" } : undefined}
              >
                {flexRender(cell.column.columnDef.cell, cell.getContext())}
              </TableCell>
            ))}
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
