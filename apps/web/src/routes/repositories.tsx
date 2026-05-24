import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { GitBranch, Trash2, RefreshCw } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type Repository } from "@/lib/api";
import { cn } from "@/lib/utils";

export function RepositoriesPage() {
  const qc = useQueryClient();
  const { data: repos, isLoading } = useQuery({
    queryKey: ["repos"],
    queryFn: api.listRepos,
    refetchInterval: 5000,
  });

  const [name, setName] = useState("");
  const [url, setUrl] = useState("");
  const [branch, setBranch] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () =>
      api.createRepo({
        name,
        url,
        ...(branch.trim() ? { default_branch: branch.trim() } : {}),
      }),
    onSuccess: () => {
      setName("");
      setUrl("");
      setBranch("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["repos"] });
    },
    onError: (e: unknown) => setError(e instanceof ApiError ? e.message : "Failed"),
  });

  const ingestMutation = useMutation({
    mutationFn: (id: string) => api.ingestRepo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repos"] }),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteRepo(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["repos"] }),
  });

  function handleCreate(e: FormEvent) {
    e.preventDefault();
    setError(null);
    createMutation.mutate();
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold">Repositories</h1>
        <p className="text-sm text-muted-foreground">
          Register a repo, run ingestion (clone → parse → chunk → embed → Qdrant).
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-4">
        <form onSubmit={handleCreate} className="grid gap-2 md:grid-cols-[1fr_2fr_140px_auto]">
          <Input
            placeholder="Display name (e.g. fastapi)"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
          />
          <Input
            placeholder="https://github.com/tiangolo/fastapi or local path"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            required
          />
          <Input
            placeholder="branch (main)"
            value={branch}
            onChange={(e) => setBranch(e.target.value)}
          />
          <Button type="submit" loading={createMutation.isPending}>Add repository</Button>
        </form>
        {error ? <div className="text-sm text-destructive mt-2">{error}</div> : null}
      </section>

      <section className="space-y-3">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : repos && repos.length > 0 ? (
          repos.map((r) => (
            <RepoCard
              key={r.id}
              repo={r}
              onIngest={() => ingestMutation.mutate(r.id)}
              onDelete={() => deleteMutation.mutate(r.id)}
              ingesting={ingestMutation.isPending && ingestMutation.variables === r.id}
            />
          ))
        ) : (
          <div className="text-sm text-muted-foreground">No repositories yet.</div>
        )}
      </section>
    </div>
  );
}

function RepoCard({
  repo,
  onIngest,
  onDelete,
  ingesting,
}: {
  repo: Repository;
  onIngest: () => void;
  onDelete: () => void;
  ingesting: boolean;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-4 flex items-start justify-between gap-4">
      <div className="min-w-0 space-y-1">
        <div className="flex items-center gap-2">
          <GitBranch className="h-4 w-4 text-muted-foreground" />
          <Link to={`/repositories/${repo.id}`} className="font-medium hover:underline">
            {repo.name}
          </Link>
          <StatusPill status={repo.status} />
        </div>
        <div className="text-xs text-muted-foreground truncate">{repo.url}</div>
        {repo.stats ? (
          <div className="text-xs text-muted-foreground">
            files: {(repo.stats as Record<string, number>).files_indexed ?? "?"} · chunks:{" "}
            {(repo.stats as Record<string, number>).chunks_indexed ?? "?"}
          </div>
        ) : null}
      </div>
      <div className="flex gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={onIngest}
          loading={ingesting || repo.status === "ingesting"}
        >
          <RefreshCw className="h-4 w-4 mr-1" /> Ingest
        </Button>
        <Button variant="ghost" size="sm" onClick={onDelete}>
          <Trash2 className="h-4 w-4 text-destructive" />
        </Button>
      </div>
    </div>
  );
}

function StatusPill({ status }: { status: Repository["status"] }) {
  const colors: Record<Repository["status"], string> = {
    new: "bg-muted text-muted-foreground",
    ingesting: "bg-amber-500/15 text-amber-500",
    ready: "bg-emerald-500/15 text-emerald-500",
    failed: "bg-destructive/15 text-destructive",
  };
  return (
    <span className={cn("text-xs rounded px-2 py-0.5", colors[status])}>{status}</span>
  );
}
