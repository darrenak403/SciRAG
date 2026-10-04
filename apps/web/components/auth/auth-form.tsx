"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Alert, AlertDescription } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { api, messageOf } from "@/lib/api-client";
import type { User } from "@/lib/types";

const COPY = {
  login: {
    title: "Sign in to ScientRAG",
    submit: "Sign in",
    busy: "Signing in…",
    other: { text: "New here?", link: "Create an account", href: "/register" },
  },
  register: {
    title: "Create your account",
    submit: "Create account",
    busy: "Creating account…",
    other: { text: "Already have an account?", link: "Sign in", href: "/login" },
  },
} as const;

export function AuthForm({ mode }: { mode: "login" | "register" }) {
  const copy = COPY[mode];
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = new FormData(event.currentTarget);
    setBusy(true);
    setError(null);
    try {
      await api<User>(`/auth/${mode}`, {
        method: "POST",
        json: { email: form.get("email"), password: form.get("password") },
      });
      router.replace("/");
    } catch (failure) {
      setError(messageOf(failure));
      setBusy(false);
    }
  }

  return (
    // POST, so a submit before the page's script has loaded never puts the password in the address.
    <form method="post" onSubmit={submit} className="flex w-full max-w-sm flex-col gap-5">
      <div className="flex flex-col gap-1">
        <p className="text-sm font-medium text-muted-foreground">ScientRAG</p>
        <h1 className="text-xl font-semibold tracking-tight">{copy.title}</h1>
      </div>

      {error && (
        <Alert variant="destructive" role="alert">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      <div className="flex flex-col gap-2">
        <Label htmlFor="email">Email</Label>
        <Input id="email" name="email" type="email" autoComplete="email" required autoFocus />
      </div>
      <div className="flex flex-col gap-2">
        <Label htmlFor="password">Password</Label>
        <Input
          id="password"
          name="password"
          type="password"
          autoComplete={mode === "login" ? "current-password" : "new-password"}
          minLength={8}
          required
        />
        {mode === "register" && <p className="text-xs text-muted-foreground">At least 8 characters.</p>}
      </div>

      <Button type="submit" size="lg" disabled={busy}>
        {busy ? copy.busy : copy.submit}
      </Button>

      <p className="text-sm text-muted-foreground">
        {copy.other.text}{" "}
        <Link href={copy.other.href} className="font-medium text-foreground underline-offset-4 hover:underline">
          {copy.other.link}
        </Link>
      </p>
    </form>
  );
}
