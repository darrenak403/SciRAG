"use client";

import { useState } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { Textarea } from "@/components/ui/textarea";
import { api, messageOf } from "@/lib/api-client";
import { addToCollection, createCollection, refreshCollections, useCollections } from "@/lib/collections";
import { plural } from "@/lib/format";
import type { Collection } from "@/lib/types";

function NameFields({ collection: current }: { collection?: Collection | null }) {
  // What the dialog opened with: a save renames the collection while the dialog is still closing.
  const [collection] = useState(current);
  return (
    <>
      <div className="flex flex-col gap-2">
        <Label htmlFor="collection-name">Name</Label>
        <Input
          id="collection-name"
          name="name"
          defaultValue={collection?.name ?? ""}
          placeholder="RAG for scientific research"
          required
          maxLength={200}
          autoFocus
        />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="collection-description">Description</Label>
        <Textarea
          id="collection-description"
          name="description"
          defaultValue={collection?.description ?? ""}
          placeholder="Optional"
          rows={2}
          maxLength={2000}
        />
      </div>
    </>
  );
}

function fields(form: HTMLFormElement) {
  const data = new FormData(form);
  return { name: String(data.get("name") ?? "").trim(), description: String(data.get("description") ?? "").trim() };
}

/** Names a new collection, or renames an existing one. */
export function CollectionFormDialog({
  open,
  collection,
  onClose,
  onSaved,
}: {
  open: boolean;
  // The collection being renamed. Without one, a new collection is made.
  collection?: Collection | null;
  onClose: () => void;
  onSaved: (collection: Collection) => void;
}) {
  const [busy, setBusy] = useState(false);

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const { name, description } = fields(event.currentTarget);
    setBusy(true);
    try {
      const saved = collection
        ? await api<Collection>(`/collections/${collection.id}`, {
            method: "PATCH",
            json: { name, description: description || null },
          })
        : await createCollection(name, description);
      if (collection) void refreshCollections();
      onSaved(saved);
      onClose();
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{collection ? "Rename collection" : "New collection"}</DialogTitle>
          <DialogDescription>
            A collection groups papers you want to ask, compare and review together.
          </DialogDescription>
        </DialogHeader>
        <form key={collection?.id ?? "new"} onSubmit={save} className="flex flex-col gap-4">
          <NameFields collection={collection} />
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Saving…" : collection ? "Save" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

const NEW = "new";

/** Puts papers into a collection: one the account already has, or a new one made here. */
export function AddToCollectionDialog({
  paperIds,
  onClose,
  onAdded,
}: {
  // null keeps the dialog closed.
  paperIds: string[] | null;
  onClose: () => void;
  onAdded?: (collection: Collection) => void;
}) {
  const collections = useCollections();
  const [chosen, setChosen] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // Nothing to choose from yet: the only thing to do is make one.
  const target = chosen ?? collections?.at(0)?.id ?? NEW;

  async function save(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!paperIds) return;
    setBusy(true);
    try {
      let collection: Collection | undefined;
      if (target === NEW) {
        const { name, description } = fields(event.currentTarget);
        collection = await createCollection(name, description, paperIds);
      } else {
        await addToCollection(target, paperIds);
        collection = collections?.find((known) => known.id === target);
      }
      if (collection) {
        toast.success(`Added to “${collection.name}”`);
        onAdded?.(collection);
      }
      setChosen(null);
      onClose();
    } catch (error) {
      toast.error(messageOf(error));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog open={paperIds !== null} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>Add to collection</DialogTitle>
          <DialogDescription>
            {paperIds && paperIds.length > 1
              ? `${plural(paperIds.length, "paper")} will be added.`
              : "The paper stays in your library; a collection only groups it with others."}
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={save} className="flex flex-col gap-4">
          {collections && collections.length > 0 && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="collection-target">Collection</Label>
              <NativeSelect id="collection-target" value={target} onChange={(event) => setChosen(event.target.value)}>
                {collections.map((collection) => (
                  <option key={collection.id} value={collection.id}>
                    {collection.name}
                  </option>
                ))}
                <option value={NEW}>New collection…</option>
              </NativeSelect>
            </div>
          )}
          {target === NEW && <NameFields />}
          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              Cancel
            </Button>
            <Button type="submit" disabled={busy || collections === null}>
              {busy ? "Adding…" : target === NEW ? "Create and add" : "Add"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
