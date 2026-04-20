import {
  LayoutDashboard,
  Bot,
  MessageSquare,
  Wrench,
  Calendar,
  Play,
  Settings,
  LogOut,
  ShieldCheck,
} from "lucide-react";
import { OcinLogo } from "@/components/OcinLogo"; // theme-adaptive logo
import { NavLink } from "@/components/NavLink";
import { useLocation, useNavigate } from "react-router-dom";
import { logout, getUser } from "@/lib/auth";
import { usePendingApprovals } from "@/hooks/use-pending-approvals";
import {
  Sidebar,
  SidebarContent,
  SidebarGroup,
  SidebarGroupContent,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarFooter,
  useSidebar,
} from "@/components/ui/sidebar";

const navItems = [
  { title: "Dashboard", url: "/", icon: LayoutDashboard },
  { title: "Chat", url: "/chat", icon: MessageSquare },
  { title: "Agents", url: "/agents", icon: Bot },
  { title: "Tools", url: "/tools", icon: Wrench },
  { title: "Schedules", url: "/schedules", icon: Calendar },
  { title: "Runs", url: "/runs", icon: Play },
  { title: "Approvals", url: "/approvals", icon: ShieldCheck },
  { title: "Settings", url: "/settings", icon: Settings },
];

export function AppSidebar() {
  const { state } = useSidebar();
  const collapsed = state === "collapsed";
  const location = useLocation();
  const navigate = useNavigate();
  const user = getUser();
  const { count: pendingCount } = usePendingApprovals();

  const handleLogout = () => {
    logout();
    navigate("/login");
  };

  return (
    <Sidebar collapsible="icon">
      <SidebarContent>
        <div className={`flex items-center gap-2 px-4 py-5 ${collapsed ? 'justify-center' : ''}`}>
          <OcinLogo size={32} />
          {!collapsed && <span className="text-lg font-semibold text-foreground tracking-tight">OCIN</span>}
        </div>

        <SidebarGroup>
          <SidebarGroupContent>
            <SidebarMenu>
              {navItems.map((item) => (
                <SidebarMenuItem key={item.title}>
                  <SidebarMenuButton asChild>
                    <NavLink
                      to={item.url}
                      end={item.url === "/"}
                      className="hover:bg-sidebar-accent relative"
                      activeClassName="bg-sidebar-accent text-primary font-medium"
                    >
                      <item.icon className="h-4 w-4 mr-2" />
                      {!collapsed && <span>{item.title}</span>}
                      {item.title === "Approvals" && pendingCount > 0 && (
                        <span className="absolute -top-1 -right-1 h-5 w-5 rounded-full bg-destructive text-destructive-foreground text-xs font-bold flex items-center justify-center shadow-lg animate-pulse">
                          {pendingCount}
                        </span>
                      )}
                    </NavLink>
                  </SidebarMenuButton>
                </SidebarMenuItem>
              ))}
            </SidebarMenu>
          </SidebarGroupContent>
        </SidebarGroup>
      </SidebarContent>

      <SidebarFooter className="border-t border-sidebar-border">
        {!collapsed && user && (
          <p className="text-xs text-muted-foreground truncate px-3 pt-3">{user.email}</p>
        )}
        <SidebarMenu>
          <SidebarMenuItem>
            <SidebarMenuButton onClick={handleLogout} className="text-muted-foreground hover:text-destructive hover:bg-destructive/10">
              <LogOut className="h-4 w-4 mr-2" />
              {!collapsed && <span>Logout</span>}
            </SidebarMenuButton>
          </SidebarMenuItem>
        </SidebarMenu>
      </SidebarFooter>
    </Sidebar>
  );
}
