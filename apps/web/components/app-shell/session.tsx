"use client";

import { createContext, useCallback, useContext, useEffect, useState } from "react";

import { Button } from "@/components/ui/button";
import { api, ApiError } from "@/lib/api-client";
import type { User } from "@/lib/types";

type Session = { user: User; refresh: () => Promise<void> };

const SessionContext = createContext<Session | null>(null);

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession needs a SessionProvider above it");
  return session;
}

/** Renders the app only for a signed-in account. Anyone else is sent to /login. */
export function SessionProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [unreachable, setUnreachable] = useState(false);

  const refresh = useCallback(async () => {
    setUser(await api<User>("/auth/me"));
  }, []);

  const load = useCallback(() => {
    setUnreachable(false);
    refresh().catch((failure: unknown) => {
      // The API client leaves /auth calls alone, so the signed-out case is handled here.
      if (failure instanceof ApiError && failure.status === 401) window.location.assign("/login");
      else setUnreachable(true);
    });
  }, [refresh]);

  useEffect(load, [load]);

  if (unreachable) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 p-6 text-center" role="alert">
        <p className="text-sm text-muted-foreground">Couldn&apos;t reach the server. Check your connection and try again.</p>
        <Button variant="outline" size="sm" onClick={load}>
          Try again
        </Button>
      </div>
    );
  }
  if (!user) return <div className="h-full" aria-busy="true" />;
  return <SessionContext.Provider value={{ user, refresh }}>{children}</SessionContext.Provider>;
}
