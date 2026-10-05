"use client";

import { ChevronsUpDown, FolderClosed, Library, LogOut, Moon, Plus, Search, Settings, Sun } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useTheme } from "next-themes";

import { useAddPaper } from "@/components/add-paper/add-paper-provider";
import { useSession } from "@/components/app-shell/session";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarGroupLabel,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarSeparator,
  useSidebar,
} from "@/components/ui/sidebar";
import { api } from "@/lib/api-client";
import { useRecentResearch } from "@/lib/research";

const RECENT_SHOWN = 8;

export function AppSidebar() {
  const pathname = usePathname();
  const { user } = useSession();
  const { open: openAddPaper } = useAddPaper();
  const { theme, setTheme } = useTheme();
  const { setOpenMobile } = useSidebar();
  const recent = useRecentResearch();

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    window.location.assign("/login");
  }

  // On a phone the sidebar is a sheet over the page: close it once a destination is chosen.
  const close = () => setOpenMobile(false);

  return (
    <Sidebar>
      <SidebarHeader>
        <Link href="/" onClick={close} className="px-2 py-1.5 text-sm font-semibold tracking-tight">
          SciRAG
        </Link>
      </SidebarHeader>

      <SidebarContent>
        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              <SidebarMenuItem>
                <SidebarMenuButton isActive={pathname === "/"} render={<Link href="/" onClick={close} />}>
                  <Search />
                  <span>Ask</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname.startsWith("/library")}
                  render={<Link href="/library" onClick={close} />}
                >
                  <Library />
                  <span>Library</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
              <SidebarMenuItem>
                <SidebarMenuButton
                  isActive={pathname.startsWith("/collections")}
                  render={<Link href="/collections" onClick={close} />}
                >
                  <FolderClosed />
                  <span>Collections</span>
                </SidebarMenuButton>
              </SidebarMenuItem>
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>

        <SidebarGroup>
          <SidebarGroupLabel>Recent</SidebarGroupLabel>
          <SidebarGroupContent>
            <SidebarMenu>
              {recent?.length === 0 && (
                <li className="px-2 py-1 text-xs text-muted-foreground">Your research sessions appear here.</li>
              )}
              {recent?.slice(0, RECENT_SHOWN).map((chat) => {
                const href = `/research/${chat.id}`;
                return (
                  <SidebarMenuItem key={chat.id}>
                    <SidebarMenuButton isActive={pathname === href} render={<Link href={href} onClick={close} />}>
                      <span className="truncate">{chat.title ?? "Untitled research"}</span>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                );
              })}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter>
        <SidebarSeparator className="mx-0" />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              onClick={() => {
                close();
                openAddPaper();
              }}
            >
              <Plus />
              <span>Add paper</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
        <SidebarSeparator className="mx-0" />
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton
              isActive={pathname.startsWith("/settings")}
              render={<Link href="/settings" onClick={close} />}
            >
              <Settings />
              <span>Settings</span>
            </SidebarMenuButton>
          </SidebarMenuItem>
          <SidebarMenuItem>
            <DropdownMenu>
              <DropdownMenuTrigger render={<SidebarMenuButton />}>
                <span className="truncate text-muted-foreground">{user.email}</span>
                <ChevronsUpDown className="ml-auto" />
              </DropdownMenuTrigger>
              <DropdownMenuContent side="top" align="start" className="min-w-48">
                <DropdownMenuItem onClick={() => setTheme(theme === "dark" ? "light" : "dark")}>
                  <Sun className="dark:hidden" />
                  <Moon className="hidden dark:block" />
                  <span className="dark:hidden">Dark theme</span>
                  <span className="hidden dark:inline">Light theme</span>
                </DropdownMenuItem>
                <DropdownMenuSeparator />
                <DropdownMenuItem onClick={signOut}>
                  <LogOut />
                  Sign out
                </DropdownMenuItem>
              </DropdownMenuContent>
            </DropdownMenu>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
