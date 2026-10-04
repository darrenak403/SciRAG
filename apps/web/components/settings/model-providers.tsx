"use client";

import { Check, Plus, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";

import { useSession } from "@/components/app-shell/session";
import { ConnectionDialog, DEFAULT_MODELS, KINDS } from "@/components/settings/connection-form";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { api, messageOf } from "@/lib/api-client";
import { plural } from "@/lib/format";
import { refreshProcessing } from "@/lib/processing-store";
import { providerProblem } from "@/lib/provider-errors";
import type { CapabilityCheck, Connection, PaperPage, UsageRow, User } from "@/lib/types";

const CHECKS: Record<string, { label: string; lost: string }> = {
  authentication: { label: "Authentication", lost: "Nothing can use this connection until the key is accepted." },
  chat: { label: "Chat", lost: "Questions can't be answered and papers can't be prepared." },
  streaming: { label: "Streaming", lost: "Answers can't be shown as they are written." },
  structured_output: {
    label: "Structured output",
    lost: "Answers still work, but search results are used in the order they were found.",
  },
  embeddings: { label: "Embeddings", lost: "Papers can't be made searchable." },
};

const ROLE_NAMES: Record<string, string> = { answer: "Answering", fast: "Fast", embedding: "Search" };

function searchModel(connection: Connection): string | undefined {
  return connection.config.models?.embedding ?? DEFAULT_MODELS[connection.kind].embedding;
}

function CheckRow({ check }: { check: CapabilityCheck }) {
  const known = CHECKS[check.check];
  const problem = providerProblem(check.error_code, check.message);
  return (
    <li className="flex items-start gap-2 text-sm">
      {check.ok ? (
        <Check className="mt-0.5 size-3.5 shrink-0 text-success" aria-label="Passed" />
      ) : (
        <X className="mt-0.5 size-3.5 shrink-0 text-destructive" aria-label="Failed" />
      )}
      <div className="min-w-0">
        <span className="font-medium">{known?.label ?? check.check}</span>
        {!check.ok && (
          <p className="text-muted-foreground">
            {problem ? `${problem.title}. ${problem.hint}` : check.message} {known?.lost}
          </p>
        )}
      </div>
    </li>
  );
}

function ConnectionCard({
  connection,
  active,
  onUse,
  onEdit,
  onTest,
  onDelete,
  testing,
}: {
  connection: Connection;
  active: boolean;
  onUse: () => void;
  onEdit: () => void;
  onTest: () => void;
  onDelete: () => void;
  testing: boolean;
}) {
  const models = { ...DEFAULT_MODELS[connection.kind], ...connection.config.models };
  const usable = connection.capabilities?.usable ?? false;
  return (
    <li className="flex flex-col gap-3 rounded-lg border p-4">
      <div className="flex flex-wrap items-start gap-2">
        <div className="min-w-0 flex-1">
          <p className="flex flex-wrap items-center gap-2 text-sm font-medium">
            {connection.label}
            {active && <Badge variant="secondary">In use</Badge>}
            {!usable && <Badge variant="outline">Not working</Badge>}
          </p>
          <p className="text-sm text-muted-foreground">
            {KINDS[connection.kind]} · key ending in {connection.secret_last4}
            {connection.config.region ? ` · ${connection.config.region}` : ""}
          </p>
          {connection.config.base_url && (
            <p className="truncate text-sm text-muted-foreground">{connection.config.base_url}</p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {!active && (
            <Button size="sm" onClick={onUse} disabled={!usable}>
              Use this connection
            </Button>
          )}
          <Button size="sm" variant="outline" onClick={onTest} disabled={testing}>
            {testing ? "Testing…" : "Test"}
          </Button>
          <Button size="sm" variant="outline" onClick={onEdit}>
            Edit
          </Button>
          <Button size="sm" variant="ghost" onClick={onDelete}>
            Delete
          </Button>
        </div>
      </div>

      <p className="text-xs text-muted-foreground">
        {Object.entries(ROLE_NAMES)
          .map(([role, name]) => `${name}: ${models[role as keyof typeof models] ?? "not chosen"}`)
          .join(" · ")}
      </p>

      {connection.capabilities && (
        <ul className="flex flex-col gap-1.5 border-t pt-3">
          {connection.capabilities.checks.map((check) => (
            <CheckRow key={check.check} check={check} />
          ))}
        </ul>
      )}
    </li>
  );
}

function Usage({ connections }: { connections: Connection[] }) {
  const [rows, setRows] = useState<UsageRow[] | null>(null);
  useEffect(() => {
    api<UsageRow[]>("/settings/providers/usage?days=30")
      .then(setRows)
      .catch(() => setRows([]));
  }, [connections]);

  const labels = new Map(connections.map((connection) => [connection.id, connection.label]));
  return (
    <section className="flex flex-col gap-2">
      <h3 className="text-sm font-medium">Usage in the last 30 days</h3>
      {rows?.length === 0 ? (
        <p className="text-sm text-muted-foreground">No model calls yet.</p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Connection</TableHead>
              <TableHead>Model</TableHead>
              <TableHead>Used for</TableHead>
              <TableHead className="text-right">Tokens in</TableHead>
              <TableHead className="text-right">Tokens out</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows?.map((row) => (
              <TableRow key={`${row.connection_id}:${row.model}:${row.role}`}>
                <TableCell>{labels.get(row.connection_id ?? "") ?? "Deleted connection"}</TableCell>
                <TableCell>{row.model}</TableCell>
                <TableCell>{ROLE_NAMES[row.role] ?? row.role}</TableCell>
                <TableCell className="text-right tabular-nums">{row.input_tokens.toLocaleString()}</TableCell>
                <TableCell className="text-right tabular-nums">{row.output_tokens.toLocaleString()}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
      <p className="text-xs text-muted-foreground">
        Token counts only. For what they cost, see the pricing page of your provider.
      </p>
    </section>
  );
}

export function ModelProviders() {
  const { user, refresh } = useSession();
  const [connections, setConnections] = useState<Connection[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [form, setForm] = useState<{ connection: Connection | null } | null>(null);
  const [testing, setTesting] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<Connection | null>(null);
  // A switch waiting for confirmation because it changes the model papers are searched with.
  const [switching, setSwitching] = useState<{ connection: Connection; papers: number } | null>(null);
  // Ready papers that were made searchable with another model than the one in use.
  const [stale, setStale] = useState(0);

  const load = useCallback(async () => {
    try {
      setConnections(await api<Connection[]>("/settings/providers"));
      setError(null);
    } catch (failure) {
      setError(messageOf(failure));
    }
  }, []);

  const countStale = useCallback(async () => {
    try {
      const page = await api<PaperPage>("/papers?status=READY&page_size=100");
      setStale(page.items.filter((paper) => paper.needs_reindex).length);
    } catch {
      // The count is a reminder only.
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);
  useEffect(() => {
    void countStale();
  }, [countStale, user.active_connection_id, connections]);

  function upsert(connection: Connection) {
    setConnections((current) =>
      current?.some((known) => known.id === connection.id)
        ? current.map((known) => (known.id === connection.id ? connection : known))
        : [...(current ?? []), connection],
    );
    // An account's first working connection is put to use by the server.
    void refresh();
  }

  async function test(connection: Connection) {
    setTesting(connection.id);
    try {
      upsert(await api<Connection>(`/settings/providers/${connection.id}/test`, { method: "POST" }));
    } catch (failure) {
      toast.error(messageOf(failure));
    } finally {
      setTesting(null);
    }
  }

  async function switchTo(connection: Connection) {
    try {
      await api<User>("/settings/active-connection", { method: "PUT", json: { connection_id: connection.id } });
      await refresh();
      setSwitching(null);
      toast.success(`Now using ${connection.label}`);
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  async function askBeforeUsing(connection: Connection) {
    const current = connections?.find((known) => known.id === user.active_connection_id);
    if (current && searchModel(current) !== searchModel(connection)) {
      const ready = await api<PaperPage>("/papers?status=READY&page_size=1").catch(() => null);
      if (ready && ready.total > 0) {
        setSwitching({ connection, papers: ready.total });
        return;
      }
    }
    await switchTo(connection);
  }

  async function remove() {
    if (!deleting) return;
    try {
      await api(`/settings/providers/${deleting.id}`, { method: "DELETE" });
      setConnections((current) => current?.filter((known) => known.id !== deleting.id) ?? null);
      setDeleting(null);
      await refresh();
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  async function reindex() {
    try {
      const { queued } = await api<{ queued: number }>("/papers/reindex", { method: "POST" });
      toast.success(`Preparing ${plural(queued, "paper")} again`);
      refreshProcessing();
      setStale(0);
    } catch (failure) {
      toast.error(messageOf(failure));
    }
  }

  return (
    <section className="flex flex-col gap-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <h2 className="text-base font-medium">Model providers</h2>
          <p className="text-sm text-muted-foreground">
            ScientRAG reads papers and answers questions with your own key. One connection is used for
            everything.
          </p>
        </div>
        <Button size="sm" onClick={() => setForm({ connection: null })}>
          <Plus /> Add connection
        </Button>
      </div>

      {error && (
        <p role="alert" className="text-sm text-destructive">
          {error}
        </p>
      )}

      {stale > 0 && (
        <Alert>
          <AlertTitle>
            {plural(stale, "paper")} {stale === 1 ? "needs" : "need"} to be prepared again
          </AlertTitle>
          <AlertDescription className="flex flex-col items-start gap-2">
            They were made searchable with another model than the one in use now, and are left out of answers
            until they are prepared again. The PDFs are not read again.
            <Button size="sm" variant="outline" onClick={reindex}>
              Re-index papers
            </Button>
          </AlertDescription>
        </Alert>
      )}

      {connections?.length === 0 && (
        <div className="flex flex-col items-center gap-3 rounded-lg border border-dashed p-8 text-center">
          <p className="text-sm font-medium">No connection yet</p>
          <p className="max-w-sm text-sm text-muted-foreground">
            Add a key from Google Gemini, AWS Bedrock, or any OpenAI-compatible service to process papers and
            ask questions.
          </p>
          <Button onClick={() => setForm({ connection: null })}>Add connection</Button>
        </div>
      )}

      {connections && connections.length > 0 && (
        <ul className="flex flex-col gap-3">
          {connections.map((connection) => (
            <ConnectionCard
              key={connection.id}
              connection={connection}
              active={connection.id === user.active_connection_id}
              testing={testing === connection.id}
              onUse={() => askBeforeUsing(connection)}
              onEdit={() => setForm({ connection })}
              onTest={() => test(connection)}
              onDelete={() => setDeleting(connection)}
            />
          ))}
        </ul>
      )}

      {connections && connections.length > 0 && <Usage connections={connections} />}

      {form && <ConnectionDialog connection={form.connection} onClose={() => setForm(null)} onSaved={upsert} />}

      <AlertDialog open={switching !== null} onOpenChange={(open) => !open && setSwitching(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Switch to {switching?.connection.label}?</AlertDialogTitle>
            <AlertDialogDescription>
              This connection searches papers with a different model. Your {plural(switching?.papers ?? 0, "ready paper")}{" "}
              will be left out of answers until {switching?.papers === 1 ? "it is" : "they are"} prepared again,
              which uses your new key.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={() => switching && switchTo(switching.connection)}>Switch</AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <AlertDialog open={deleting !== null} onOpenChange={(open) => !open && setDeleting(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete {deleting?.label}?</AlertDialogTitle>
            <AlertDialogDescription>
              The saved key is removed.
              {deleting?.id === user.active_connection_id &&
                " This is the connection in use: questions and paper processing stop until you choose another."}
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={remove}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </section>
  );
}
