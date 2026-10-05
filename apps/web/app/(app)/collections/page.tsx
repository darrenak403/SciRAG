"use client";

import { Plus } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/app-shell/page-header";
import { CollectionFormDialog } from "@/components/collections/collection-dialogs";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { refreshCollections, useCollections } from "@/lib/collections";
import { plural, relativeDay } from "@/lib/format";

export default function CollectionsPage() {
  const router = useRouter();
  const collections = useCollections();
  const [creating, setCreating] = useState(false);

  // The shared list may be older than what this page is opened to show.
  useEffect(() => {
    void refreshCollections();
  }, []);

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Collections">
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus /> New collection
        </Button>
      </PageHeader>

      <div className="flex min-h-0 flex-1 flex-col overflow-y-auto p-4">
        {collections === null ? (
          <div className="mx-auto flex w-full max-w-3xl flex-col gap-2" aria-busy="true">
            {Array.from({ length: 3 }, (_, index) => (
              <Skeleton key={index} className="h-16" />
            ))}
          </div>
        ) : collections.length === 0 ? (
          <div className="m-auto flex max-w-sm flex-col items-center gap-3 text-center">
            <h2 className="text-base font-medium">No collections yet</h2>
            <p className="text-sm text-muted-foreground">
              Group papers on one topic to ask them together, compare them side by side, or get a review across
              all of them.
            </p>
            <Button onClick={() => setCreating(true)}>New collection</Button>
          </div>
        ) : (
          <ul className="mx-auto flex w-full max-w-3xl flex-col divide-y rounded-lg border">
            {collections.map((collection) => (
              <li key={collection.id}>
                <Link href={`/collections/${collection.id}`} className="flex flex-col gap-0.5 px-4 py-3 hover:bg-muted">
                  <span className="flex items-baseline gap-3">
                    <span className="min-w-0 flex-1 truncate text-sm font-medium">{collection.name}</span>
                    <span className="shrink-0 text-xs text-muted-foreground">
                      {plural(collection.paper_ids.length, "paper")} · {relativeDay(collection.updated_at)}
                    </span>
                  </span>
                  {collection.description && (
                    <span className="line-clamp-1 text-sm text-muted-foreground">{collection.description}</span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>

      <CollectionFormDialog
        open={creating}
        onClose={() => setCreating(false)}
        onSaved={(collection) => router.push(`/collections/${collection.id}`)}
      />
    </div>
  );
}
