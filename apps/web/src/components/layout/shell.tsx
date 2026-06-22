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
  Settings,
  Sparkles,
  Workflow,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { SANDBOX_ENABLED } from "@/lib/features";
import { useAuthStore } from "@/stores/auth-store";
import { cn, initials } from "@/lib/utils";

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
    <div className="grid min-h-screen grid-cols-[16rem_1fr] bg-background">
      <aside className="relative flex flex-col border-r border-border bg-card/30 backdrop-blur-xl">
        {/* subtle top glow */}
        <div className="pointer-events-none absolute inset-x-0 top-0 h-40 bg-gradient-to-b from-sky-500/[0.07] to-transparent" />

        {/* brand */}
        <div className="relative flex items-center gap-2.5 px-4 py-4">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-indigo-500 shadow-lg shadow-sky-500/20">
            <Sparkles className="h-5 w-5 text-white" />
          </div>
          <span className="font-semibold tracking-tight">AI Coding Agent</span>
        </div>

        {/* nav */}
        <nav className="relative flex-1 space-y-1 px-3 py-2">
          <p className="px-2 pb-1 text-[10px] font-semibold uppercase tracking-wider text-muted-foreground/60">
            Workspace
          </p>
          <NavItem to="/dashboard" icon={<LayoutDashboard className="h-4 w-4" />} label="Dashboard" />
          <NavItem to="/repositories" icon={<GitBranch className="h-4 w-4" />} label="Repositories" />
          <NavItem to="/search" icon={<Search className="h-4 w-4" />} label="Search" />
          <NavItem to="/chat" icon={<MessageSquare className="h-4 w-4" />} label="Chat" />
          <NavItem to="/agents" icon={<Workflow className="h-4 w-4" />} label="Agents" />
          <NavItem to="/memory" icon={<Brain className="h-4 w-4" />} label="Memory" />
          {SANDBOX_ENABLED ? (
            <NavItem to="/sandbox" icon={<Terminal className="h-4 w-4" />} label="Sandbox" />
          ) : null}
          <NavItem to="/github" icon={<Github className="h-4 w-4" />} label="GitHub" />
          <NavItem to="/settings" icon={<Settings className="h-4 w-4" />} label="Settings" />
        </nav>

        {/* account footer */}
        <div className="relative space-y-3 border-t border-border p-3">
          <div className="flex items-center gap-2.5 px-1">
            <div className="grid h-8 w-8 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-xs font-semibold text-white">
              {initials(user?.full_name || user?.email || "?")}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium">{user?.full_name || "Account"}</div>
              <div className="truncate text-xs text-muted-foreground">{user?.email ?? "—"}</div>
            </div>
          </div>
          <Button variant="outline" size="sm" className="w-full" onClick={handleLogout}>
            <LogOut className="mr-2 h-4 w-4" /> Sign out
          </Button>
        </div>
      </aside>

      <main className="overflow-auto p-6">
        <Outlet />
      </main>
    </div>
  );
}

function NavItem({ to, icon, label }: { to: string; icon: React.ReactNode; label: string }) {
  return (
    <NavLink to={to} className="group relative block">
      {({ isActive }) => (
        <div
          className={cn(
            "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition-colors",
            isActive
              ? "bg-primary/10 font-medium text-foreground"
              : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
          )}
        >
          {isActive ? (
            <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-sky-400 to-indigo-500" />
          ) : null}
          <span
            className={cn(
              "transition-colors",
              isActive ? "text-primary" : "text-muted-foreground group-hover:text-foreground",
            )}
          >
            {icon}
          </span>
          <span>{label}</span>
        </div>
      )}
    </NavLink>
  );
}
