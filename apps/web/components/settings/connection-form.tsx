"use client";

import { useEffect, useState } from "react";

import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { NativeSelect } from "@/components/ui/native-select";
import { api, ApiError, messageOf } from "@/lib/api-client";
import { providerProblem } from "@/lib/provider-errors";
import type { Connection, ConnectionKind } from "@/lib/types";

export const KINDS: Record<ConnectionKind, string> = {
  gemini: "Google Gemini",
  bedrock: "AWS Bedrock",
  openai_compatible: "OpenAI-compatible",
};

const ROLES = [
  { name: "answer", label: "Answering model", hint: "Writes the answers." },
  { name: "fast", label: "Fast model", hint: "Reads papers and ranks search results." },
  { name: "embedding", label: "Search model", hint: "Makes papers searchable." },
] as const;

// What the server uses when a model is left blank. Kept in step with providers/defaults.py.
export const DEFAULT_MODELS: Record<ConnectionKind, Partial<Record<(typeof ROLES)[number]["name"], string>>> = {
  gemini: { answer: "gemini-3.5-flash", fast: "gemini-3.5-flash-lite", embedding: "gemini-embedding-2" },
  bedrock: {
    answer: "amazon.nova-pro-v1:0",
    fast: "amazon.nova-lite-v1:0",
    embedding: "amazon.titan-embed-text-v2:0",
  },
  openai_compatible: {},
};

function text(form: FormData, name: string): string {
  return String(form.get(name) ?? "").trim();
}

function modelsOf(form: FormData): Record<string, string> {
  return Object.fromEntries(ROLES.map(({ name }) => [name, text(form, `model-${name}`)]).filter(([, value]) => value));
}

function Secret({ id, label, editing }: { id: string; label: string; editing: boolean }) {
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>{label}</Label>
      {/* Never filled in with the saved value: the server does not send it back. */}
      <Input
        id={id}
        name={id}
        type="password"
        autoComplete="new-password"
        required={!editing}
        minLength={8}
        placeholder={editing ? "Leave blank to keep the saved one" : undefined}
      />
    </div>
  );
}

/**
 * Adds a connection or changes one. Saving runs the connection test, so the dialog
 * stays open until the provider has answered. Mounted only while it is open.
 */
export function ConnectionDialog({
  connection,
  onClose,
  onSaved,
}: {
  // The connection to change; null adds a new one.
  connection: Connection | null;
  onClose: () => void;
  onSaved: (connection: Connection) => void;
}) {
  const [kind, setKind] = useState<ConnectionKind>("gemini");
  // A router's connection is saved first, without models, so that its model list can be read.
  const [saved, setSaved] = useState<Connection | null>(null);
  const [available, setAvailable] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<{ title: string; hint: string } | null>(null);

  const editing = connection ?? saved;
  const shownKind = editing?.kind ?? kind;
  const choosesModels = shownKind === "openai_compatible";

  // The models the saved key can use, offered as suggestions for each role.
  useEffect(() => {
    if (!editing || editing.kind !== "openai_compatible") return;
    let cancelled = false;
    api<{ models: string[] }>(`/settings/providers/${editing.id}/models`)
      .then(({ models }) => !cancelled && setAvailable(models))
      .catch((failure: unknown) => {
        if (cancelled) return;
        const code = failure instanceof ApiError ? failure.code : null;
        const problem = providerProblem(code, messageOf(failure));
        setError(problem ?? { title: "Couldn't read the model list", hint: messageOf(failure) });
      });
    return () => {
      cancelled = true;
    };
  }, [editing]);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      if (editing) {
        const credentials = Object.fromEntries(
          ["api_key", "access_key_id", "secret_access_key"]
            .map((name) => [name, text(form, name)])
            .filter(([, value]) => value),
        );
        const result = await api<Connection>(`/settings/providers/${editing.id}`, {
          method: "PATCH",
          json: { label: text(form, "label"), models: modelsOf(form), ...credentials },
        });
        onSaved(result);
        onClose();
      } else {
        const result = await api<Connection>("/settings/providers", {
          method: "POST",
          json: {
            kind,
            label: text(form, "label"),
            models: modelsOf(form),
            ...(kind === "bedrock"
              ? {
                  region: text(form, "region"),
                  access_key_id: text(form, "access_key_id"),
                  secret_access_key: text(form, "secret_access_key"),
                }
              : { api_key: text(form, "api_key") }),
            ...(kind === "openai_compatible" ? { base_url: text(form, "base_url") } : {}),
          },
        });
        onSaved(result);
        if (kind === "openai_compatible") setSaved(result);
        else onClose();
      }
    } catch (failure) {
      setError({ title: "Couldn't save the connection", hint: messageOf(failure) });
    } finally {
      setBusy(false);
    }
  }

  const models = (
    <div className="flex flex-col gap-3">
      {ROLES.map(({ name, label, hint }) => (
        <div key={name} className="flex flex-col gap-1.5">
          <Label htmlFor={`model-${name}`}>{label}</Label>
          <Input
            id={`model-${name}`}
            name={`model-${name}`}
            list={choosesModels ? "available-models" : undefined}
            defaultValue={editing?.config.models?.[name] ?? ""}
            placeholder={DEFAULT_MODELS[shownKind][name] ?? "Choose a model"}
            required={choosesModels}
            maxLength={200}
          />
          <p className="text-xs text-muted-foreground">{hint}</p>
        </div>
      ))}
      <datalist id="available-models">
        {available.map((model) => (
          <option key={model} value={model} />
        ))}
      </datalist>
    </div>
  );

  return (
    <Dialog open onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>{connection ? "Edit connection" : saved ? "Choose models" : "Add a connection"}</DialogTitle>
          <DialogDescription>
            {saved
              ? "The connection is saved. Pick the model for each job, then save to test it."
              : "Your key is stored encrypted and is only used for your own papers and questions."}
          </DialogDescription>
        </DialogHeader>

        {/* Keyed so the fields start over when the kind or the connection changes. */}
        <form key={`${editing?.id ?? "new"}:${shownKind}`} onSubmit={submit} className="flex flex-col gap-4">
          {!editing && (
            <div className="flex flex-col gap-2">
              <Label htmlFor="kind">Provider</Label>
              <NativeSelect id="kind" value={kind} onChange={(event) => setKind(event.target.value as ConnectionKind)}>
                {Object.entries(KINDS).map(([value, label]) => (
                  <option key={value} value={value}>
                    {label}
                  </option>
                ))}
              </NativeSelect>
            </div>
          )}

          <div className="flex flex-col gap-2">
            <Label htmlFor="label">Name</Label>
            <Input
              id="label"
              name="label"
              defaultValue={editing?.label ?? KINDS[shownKind]}
              required
              maxLength={100}
            />
          </div>

          {!saved && (
            <>
              {shownKind === "openai_compatible" && !editing && (
                <div className="flex flex-col gap-2">
                  <Label htmlFor="base_url">Base URL</Label>
                  <Input id="base_url" name="base_url" type="url" required placeholder="https://router.example.com/v1" />
                </div>
              )}
              {shownKind === "bedrock" ? (
                <>
                  {!editing && (
                    <div className="flex flex-col gap-2">
                      <Label htmlFor="region">Region</Label>
                      <Input id="region" name="region" required placeholder="us-east-1" pattern="[a-z]{2}(-[a-z]+)+-\d" />
                    </div>
                  )}
                  <Secret id="access_key_id" label="Access key ID" editing={!!editing} />
                  <Secret id="secret_access_key" label="Secret access key" editing={!!editing} />
                </>
              ) : (
                <Secret id="api_key" label="API key" editing={!!editing} />
              )}
            </>
          )}

          {choosesModels ? (
            // A router offers no defaults; its model list is only known once the key is saved.
            editing && models
          ) : (
            <details className="rounded-lg border px-3 py-2">
              <summary className="cursor-pointer text-sm font-medium">Advanced</summary>
              <p className="py-2 text-xs text-muted-foreground">
                Leave a model blank to use the default shown in the field.
              </p>
              {models}
            </details>
          )}

          {error && (
            <Alert variant="destructive" role="alert">
              <AlertTitle>{error.title}</AlertTitle>
              <AlertDescription>{error.hint}</AlertDescription>
            </Alert>
          )}

          <DialogFooter>
            <Button type="button" variant="outline" onClick={onClose}>
              {saved ? "Later" : "Cancel"}
            </Button>
            <Button type="submit" disabled={busy}>
              {busy ? "Testing connection…" : choosesModels && !editing ? "Connect" : "Save and test"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
