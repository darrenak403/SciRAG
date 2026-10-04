"use client";

import { useTheme } from "next-themes";

import { PageHeader } from "@/components/app-shell/page-header";
import { useSession } from "@/components/app-shell/session";
import { ModelProviders } from "@/components/settings/model-providers";
import { Button } from "@/components/ui/button";
import { NativeSelect } from "@/components/ui/native-select";
import { Separator } from "@/components/ui/separator";
import { api } from "@/lib/api-client";

export default function SettingsPage() {
  const { user } = useSession();
  const { theme, setTheme } = useTheme();

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    window.location.assign("/login");
  }

  return (
    <div className="flex h-full flex-col">
      <PageHeader title="Settings" />
      <div className="min-h-0 flex-1 overflow-y-auto">
        <div className="mx-auto flex w-full max-w-3xl flex-col gap-8 p-4 pb-24">
          <ModelProviders />

          <Separator />

          <section className="flex flex-col gap-3">
            <h2 className="text-base font-medium">Appearance</h2>
            <label className="flex items-center justify-between gap-3 text-sm">
              Theme
              <NativeSelect value={theme ?? "system"} onChange={(event) => setTheme(event.target.value)} className="w-40">
                <option value="system">System</option>
                <option value="light">Light</option>
                <option value="dark">Dark</option>
              </NativeSelect>
            </label>
          </section>

          <Separator />

          <section className="flex flex-col gap-3">
            <h2 className="text-base font-medium">Account</h2>
            <div className="flex items-center justify-between gap-3 text-sm">
              <span className="min-w-0 truncate text-muted-foreground">{user.email}</span>
              <Button variant="outline" size="sm" onClick={signOut}>
                Sign out
              </Button>
            </div>
          </section>
        </div>
      </div>
    </div>
  );
}
