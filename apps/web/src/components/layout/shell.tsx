import { Outlet, NavLink } from "react-router-dom";
import {
  LogOut,
  LayoutDashboard,
  GitBranch,
  Search,
  MessageSquare,
  Brain,
  Terminal,
  Github,
  Sparkles,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

export function AppShell() {
  const user = useAuthStore((s) => s.user);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const clear = useAuthStore((s) => s.clear);

  async function handleLogout() {
    try {
      if (refreshToken) await api.logout(refreshToken);
    } catch {
      // ignore — clearing tokens client-side is enough to lock out the SPA
    }
    clear();
    window.location.assign("/login");
  }

  return (
    <div className="min-h-screen grid grid-cols-[16rem_1fr]">
      <aside className="border-r border-border bg-card/40 flex flex-col">
        <div className="p-4 flex items-center gap-2 font-semibold">
          <Sparkles className="h-5 w-5 text-primary" />
          <span>AI Coding Agent</span>
        </div>
        <nav className="flex-1 px-2 space-y-1">
          <NavItem to="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
          <NavItem to="/repositories" icon={<GitBranch className="h-4 w-4" />} label="Repositories" />
          <NavItem to="/search" icon={<Search className="h-4 w-4" />} label="Search" />
          <NavItem to="/chat" icon={<MessageSquare className="h-4 w-4" />} label="Chat" />
          <NavItem to="/memory" icon={<Brain className="h-4 w-4" />} label="Memory" />
          <NavItem to="/sandbox" icon={<Terminal className="h-4 w-4" />} label="Sandbox" />
          <NavItem to="/github" icon={<Github className="h-4 w-4" />} label="GitHub" />
        </nav>
        <div className="p-3 border-t border-border space-y-2">
          <div className="text-xs text-muted-foreground truncate">
            {user?.email ?? "—"}
          </div>
          <Button variant="outline" size="sm" className="w-full" onClick={handleLogout}>
            <LogOut className="h-4 w-4 mr-2" /> Sign out
          </Button>
        </div>
      </aside>
      <main className="p-6 overflow-auto">
        <Outlet />
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        cn(
          "flex items-center gap-2 rounded-md px-3 py-2 text-sm",
          isActive
            ? "bg-accent text-accent-foreground"
            : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
        )
      }
    >
      {icon}
      <span>{label}</span>
    </NavLink>
  );
}
