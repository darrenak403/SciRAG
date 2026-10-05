"use client";

import {
  type ColumnDef,
  flexRender,
  getCoreRowModel,
  useReactTable,
} from "@tanstack/react-table";
import Link from "next/link";
import { createContext, useContext, useMemo } from "react";

import { CitationMarker } from "@/components/research/citation-marker";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { Comparison, ComparisonCell, Source } from "@/lib/types";

type Row = Comparison["rows"][number];

// What the cells need that changes while the table stays the same. Read from here, the
// column definitions keep their identity, and a cell is not remounted (losing focus)
// each time a passage is opened or the conversation below moves on.
const Opening = createContext<{
  byMarker: Map<string, Source>;
  activeChunk: string | null;
  onOpen: (source: Source) => void;
} | null>(null);

/** One cell of the comparison. Choosing it opens the passage it rests on. */
function EvidenceCell({ cell }: { cell: ComparisonCell }) {
  const opening = useContext(Opening);
  if (!opening) return null;
  const { byMarker, activeChunk, onOpen } = opening;
  // The passages this cell cites, in the order it cites them.
  const sources = cell.markers.flatMap((marker) => byMarker.get(marker) ?? []);
  const first = sources.at(0);
  if (!first) return <span className="text-muted-foreground">{cell.text}</span>;
  return (
    <>
      <button
        type="button"
        onClick={() => onOpen(first)}
        className="rounded-sm text-left underline-offset-4 outline-none hover:underline focus-visible:ring-2 focus-visible:ring-citation/50"
      >
        {cell.text}
      </button>
      {sources.map((source) => (
        <CitationMarker
          key={source.marker}
          source={source}
          active={activeChunk === source.chunk_id}
          onOpen={onOpen}
        />
      ))}
    </>
  );
}

/** Papers side by side: a row for each paper, a column for each thing compared. */
export function ComparisonTable({
  table,
  sources,
  activeChunk,
  onOpen,
}: {
  table: Comparison;
  sources: Source[];
  activeChunk: string | null;
  onOpen: (source: Source) => void;
}) {
  const opening = useMemo(
    () => ({
      byMarker: new Map(sources.map((source) => [source.marker, source])),
      activeChunk,
      onOpen,
    }),
    [sources, activeChunk, onOpen],
  );
  const columns = useMemo<ColumnDef<Row>[]>(
    () => [
      {
        id: "paper",
        header: "Paper",
        cell: ({ row: { original: row } }) => (
          <Link
            href={`/library/${row.paper_id}`}
            className="line-clamp-3 font-medium hover:underline"
          >
            {row.paper_title}
          </Link>
        ),
      },
      ...table.columns.map((name, index): ColumnDef<Row> => ({
        id: `column-${index}`,
        header: name,
        cell: ({ row: { original: row } }) => (
          <EvidenceCell cell={row.cells[index]} />
        ),
      })),
    ],
    [table.columns],
  );

  const grid = useReactTable({
    data: table.rows,
    columns,
    getCoreRowModel: getCoreRowModel(),
    getRowId: (row) => row.paper_id,
  });

  return (
    <Opening value={opening}>
      <div className="rounded-lg border">
        <Table aria-label="Comparison of the papers">
          <TableHeader>
            {grid.getHeaderGroups().map((group) => (
              <TableRow key={group.id}>
                {group.headers.map((header) => (
                  <TableHead
                    key={header.id}
                    className="h-auto py-2 align-bottom whitespace-normal"
                  >
                    {flexRender(
                      header.column.columnDef.header,
                      header.getContext(),
                    )}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {grid.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell
                    key={cell.id}
                    className="min-w-36 align-top whitespace-normal"
                  >
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </Opening>
  );
}
