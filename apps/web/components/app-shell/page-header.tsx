import { SidebarTrigger } from "@/components/ui/sidebar";

/** The bar at the top of a page: sidebar toggle, title, and the page's own actions. */
export function PageHeader({ title, children }: { title: React.ReactNode; children?: React.ReactNode }) {
  return (
    <header className="flex h-12 shrink-0 items-center gap-2 border-b px-3">
      <SidebarTrigger />
      <h1 className="min-w-0 flex-1 truncate text-sm font-medium">{title}</h1>
      {children}
    </header>
  );
}
