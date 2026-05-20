import { useQuery } from "@tanstack/react-query";

import { api } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

export function DashboardPage() {
  const user = useAuthStore((s) => s.user);
  const { data: ready } = useQuery({
    queryKey: ["ready"],
    queryFn: api.ready,
    refetchInterval: 10_000,
  });

  return (
    <div className="space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Welcome{user?.full_name ? `, ${user.full_name}` : ""}</h1>
        <p className="text-sm text-muted-foreground">
          Phase 1 is live. Repository ingestion, RAG, and agents land in the upcoming phases.
        </p>
      </header>

      <section className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card title="You">
          <div className="text-sm space-y-1">
            <div><span className="text-muted-foreground">email:</span> {user?.email}</div>
            <div><span className="text-muted-foreground">id:</span> <code className="text-xs">{user?.id}</code></div>
            <div>
              <span className="text-muted-foreground">roles:</span>{" "}
              {user?.roles.map((r) => r.name).join(", ") || "—"}
            </div>
          </div>
        </Card>

        <Card title="Platform status">
          <div className="text-sm space-y-1">
            <Row label="overall" value={ready?.status ?? "…"} />
            {ready
              ? Object.entries(ready.checks).map(([k, v]) => <Row key={k} label={k} value={v} />)
              : null}
          </div>
        </Card>

        <Card title="Roadmap">
          <ul className="text-sm space-y-1 list-disc pl-4">
            <li>Phase 2 — repository ingestion + embeddings</li>
            <li>Phase 3 — RAG + context engine</li>
            <li>Phase 4 — LangGraph agents</li>
            <li>Phase 5 — sandboxed terminal</li>
          </ul>
        </Card>
      </section>
    </div>
  );
}

function Card({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-border bg-card text-card-foreground p-4">
      <div className="text-sm font-medium mb-2">{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value }: { label: string; value: string }) {
  const ok = value === "ok";
  return (
    <div className="flex justify-between gap-3">
      <span className="text-muted-foreground">{label}</span>
      <span className={ok ? "text-emerald-500" : "text-amber-500"}>{value}</span>
    </div>
  );
}
