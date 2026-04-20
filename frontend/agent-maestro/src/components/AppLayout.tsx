import { SidebarProvider, SidebarTrigger } from "@/components/ui/sidebar";
import { AppSidebar } from "@/components/AppSidebar";
import { ContainerStatusPill } from "@/components/ContainerStatusPill";
import { getUser } from "@/lib/auth";

export function AppLayout({ children }: { children: React.ReactNode }) {
  const user = getUser();

  return (
    <SidebarProvider>
      <div className="h-screen overflow-hidden flex w-full">
        <AppSidebar />
        <div className="flex-1 flex flex-col overflow-hidden min-w-0">
          <header className="flex-shrink-0 h-14 flex items-center justify-between border-b border-border px-4 bg-card/50 backdrop-blur-sm">
            <div className="flex items-center gap-3">
              <SidebarTrigger className="text-muted-foreground hover:text-foreground" />
            </div>
            <div className="flex items-center gap-4">
              <ContainerStatusPill />
              {user && (
                <span className="text-sm text-muted-foreground hidden md:inline">{user.email}</span>
              )}
            </div>
          </header>
          <main className="flex-1 overflow-y-auto min-h-0 flex flex-col">
            {children}
          </main>
        </div>
      </div>
    </SidebarProvider>
  );
}
