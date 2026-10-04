import { AddPaperProvider } from "@/components/add-paper/add-paper-provider";
import { AppSidebar } from "@/components/app-shell/app-sidebar";
import { ProcessingWidget } from "@/components/app-shell/processing-widget";
import { SessionProvider } from "@/components/app-shell/session";
import { SidebarInset, SidebarProvider } from "@/components/ui/sidebar";

export default function AppLayout({ children }: LayoutProps<"/">) {
  return (
    <SessionProvider>
      <AddPaperProvider>
        <SidebarProvider className="h-full min-h-0">
          <AppSidebar />
          <SidebarInset className="min-w-0 overflow-hidden">{children}</SidebarInset>
        </SidebarProvider>
        <ProcessingWidget />
      </AddPaperProvider>
    </SessionProvider>
  );
}
