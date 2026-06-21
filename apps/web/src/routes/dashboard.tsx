import type { ComponentType, ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  GitBranch,
  Search,
  MessageSquare,
  Brain,
  ArrowRight,
  Activity,
  CheckCircle2,
  Clock,
} from "lucide-react";

import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

const QUICK_ACTIONS: {
  to: string;
  icon: ComponentType<{ className?: string }>;
  title: string;
  desc: string;
  grad: string;
}[] = [
  { to: "/repositories", icon: GitBranch, title: "Repositories", desc: "Ingest & index a repo", grad: "from-sky-400 to-cyan-500" },
  { to: "/search", icon: Search, title: "Search", desc: "Find code semantically", grad: "from-indigo-400 to-violet-500" },
  { to: "/chat", icon: MessageSquare, title: "Chat", desc: "Ask about your code", grad: "from-fuchsia-400 to-pink-500" },
  { to: "/memory", icon: Brain, title: "Memory", desc: "Durable facts & recall", grad: "from-amber-400 to-orange-500" },
];

const ROADMAP: { done: boolean; text: string }[] = [
  { done: true, text: "Repository ingestion & embeddings" },
  { done: true, text: "Hybrid search + RAG chat" },
  { done: true, text: "Sandbox & GitHub PR review" },
  { done: false, text: "Phase 10 — orgs, SSO & billing" },
];

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data: ready } = useQuery({
    queryKey: ["ready"],
    queryFn: api.ready,
    refetchInterval: 10_000,
  });

  const displayName = user?.full_name?.trim() || user?.email || "there";
  const initials = initialsOf(user?.full_name || user?.email || "?");
  const greeting = greetingForNow();
  const role = user?.roles.map((r) => r.name).join(", ") || "member";

  return (
    <div className="relative space-y-8">
      {/* soft glow behind the header */}
      <div className="pointer-events-none absolute -top-24 right-0 h-72 w-72 rounded-full bg-indigo-500/10 blur-3xl" />

      <header className="relative space-y-2">
        <h1 className="text-3xl font-bold tracking-tight">
          {greeting},{" "}
          <span className="bg-gradient-to-r from-sky-400 to-indigo-400 bg-clip-text text-transparent">
            {displayName}
          </span>
        </h1>
        <p className="text-sm text-muted-foreground">
          Your AI coding workspace — ingest a repo, then search, chat, and review across it.
        </p>
      </header>

      {/* ---- quick actions ---- */}
      <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {QUICK_ACTIONS.map((a) => {
          const Icon = a.icon;
          return (
            <Link
              key={a.to}
              to={a.to}
              className="group rounded-xl border border-border bg-card/60 p-5 backdrop-blur transition-all hover:-translate-y-0.5 hover:border-primary/40 hover:shadow-lg hover:shadow-primary/5"
            >
              <div className="flex items-start justify-between">
                <div className={`grid h-10 w-10 place-items-center rounded-lg bg-gradient-to-br ${a.grad} shadow-md`}>
                  <Icon className="h-5 w-5 text-white" />
                </div>
                <ArrowRight className="h-4 w-4 text-muted-foreground transition-all group-hover:translate-x-0.5 group-hover:text-foreground" />
              </div>
              <div className="mt-4 font-medium">{a.title}</div>
              <div className="text-sm text-muted-foreground">{a.desc}</div>
            </Link>
          );
        })}
      </section>

      {/* ---- detail cards ---- */}
      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        {/* account */}
        <Card title="Your account">
          <div className="flex items-center gap-3">
            <div className="grid h-12 w-12 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-sm font-semibold text-white">
              {initials}
            </div>
            <div className="min-w-0">
              <div className="truncate font-medium">{user?.full_name || user?.email}</div>
              <div className="truncate text-sm text-muted-foreground">{user?.email}</div>
            </div>
          </div>
          <div className="mt-4 space-y-2 text-sm">
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">Role</span>
              <span className="rounded-full border border-border bg-accent/50 px-2 py-0.5 text-xs capitalize">
                {role}
              </span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-muted-foreground">User ID</span>
              <code className="truncate text-xs text-muted-foreground">{user?.id}</code>
            </div>
          </div>
        </Card>

        {/* platform status */}
        <Card title="Platform status" icon={<Activity className="h-4 w-4 text-muted-foreground" />}>
          <div className="space-y-2.5 text-sm">
            <StatusRow label="Overall" value={ready?.status ?? "checking…"} />
            {ready
              ? Object.entries(ready.checks).map(([k, v]) => (
                  <StatusRow key={k} label={k} value={v} />
                ))
              : null}
          </div>
        </Card>

        {/* roadmap */}
        <Card title="What's shipped">
          <ul className="space-y-2.5 text-sm">
            {ROADMAP.map((r) => (
              <li key={r.text} className="flex items-center gap-2.5">
                {r.done ? (
                  <CheckCircle2 className="h-4 w-4 shrink-0 text-emerald-500" />
                ) : (
                  <Clock className="h-4 w-4 shrink-0 text-muted-foreground" />
                )}
                <span className={r.done ? "" : "text-muted-foreground"}>{r.text}</span>
              </li>
            ))}
          </ul>
        </Card>
      </section>
    </div>
  );
}

// ---------- helpers ----------

function greetingForNow(): string {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

function initialsOf(raw: string): string {
  const parts = raw.trim().split(/[\s@._-]+/).filter(Boolean);
  const a = parts[0] ?? "";
  const b = parts.length > 1 ? parts[1] ?? "" : "";
  const initials = (a.charAt(0) + b.charAt(0)).toUpperCase();
  if (initials.length >= 2) return initials;
  if (a.length >= 2) return a.slice(0, 2).toUpperCase();
  return (a.charAt(0) || "?").toUpperCase();
}

function Card({
  title,
  icon,
  children,
}: {
  title: string;
  icon?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-5 backdrop-blur">
      <div className="mb-3 flex items-center gap-2 text-sm font-medium">
        {icon}
        <span>{title}</span>
      </div>
      {children}
    </div>
  );
}

function StatusRow({ label, value }: { label: string; value: string }) {
  const color = value === "ok" ? "bg-emerald-500" : value.startsWith("error") ? "bg-red-500" : "bg-amber-500";
  const text = value === "ok" ? "text-emerald-500" : value.startsWith("error") ? "text-red-500" : "text-amber-500";
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="capitalize text-muted-foreground">{label}</span>
      <span className="flex items-center gap-2">
        <span className={`h-1.5 w-1.5 rounded-full ${color}`} />
        <span className={text}>{value}</span>
      </span>
    </div>
  );
}
