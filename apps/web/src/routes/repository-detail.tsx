import { useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";

import { api, type IngestJob } from "@/lib/api";
import { readSse } from "@/lib/sse";
import { useReposStore } from "@/stores/repos-store";
import { useAuthStore } from "@/stores/auth-store";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

export function RepositoryDetailPage() {
  const { id } = useParams<{ id: string }>();
  const repoId = id!;

  const { data: repo } = useQuery({
    queryKey: ["repo", repoId],
    queryFn: () => api.getRepo(repoId),
    refetchInterval: 5000,
  });

  const { data: jobs } = useQuery({
    queryKey: ["jobs", repoId],
    queryFn: () => api.listJobs(repoId),
    refetchInterval: 5000,
  });

  const currentJob = jobs?.[0];

  return (
    <div className="space-y-6 max-w-5xl">
      <Link to="/repositories" className="text-sm text-muted-foreground hover:underline">
        ← All repositories
      </Link>
      <header>
        <h1 className="text-2xl font-semibold">{repo?.name ?? "…"}</h1>
        <div className="text-xs text-muted-foreground">{repo?.url}</div>
      </header>

      {currentJob ? <JobPanel repoId={repoId} job={currentJob} /> : null}

      <section>
        <h2 className="text-sm font-medium mb-2">Recent jobs</h2>
        <div className="space-y-2">
          {(jobs ?? []).map((j) => (
            <div key={j.id} className="rounded border border-border bg-card p-3 text-sm">
              <div className="flex justify-between">
                <span>{j.status}</span>
                <code className="text-xs text-muted-foreground">{j.id.slice(0, 8)}</code>
              </div>
              <div className="text-xs text-muted-foreground">
                files: {j.files_indexed}/{j.files_seen} · chunks: {j.chunks_indexed}
              </div>
              {j.error ? (
                <div className="text-xs text-destructive mt-1 break-words">{j.error}</div>
              ) : null}
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function JobPanel({ repoId, job }: { repoId: string; job: IngestJob }) {
  const progress = useReposStore((s) => s.progressByJobId[job.id]);
  const update = useReposStore((s) => s.updateProgress);
  const reset = useReposStore((s) => s.reset);
  const [_, setBeat] = useState(0);

  useEffect(() => {
    if (job.status !== "queued" && job.status !== "running") return;
    const ctrl = new AbortController();

    (async () => {
      try {
        const access = useAuthStore.getState().accessToken;
        if (!access) return;
        const url = `${BASE_URL}/api/v1/repositories/${repoId}/jobs/${job.id}/events`;
        for await (const ev of readSse(url, { signal: ctrl.signal })) {
          if (ev.event === "ping") {
            setBeat((b) => b + 1);
            continue;
          }
          try {
            const parsed = JSON.parse(ev.data);
            update(job.id, {
              status: parsed.status ?? "running",
              filesSeen: parsed.files_seen,
              filesIndexed: parsed.files_indexed,
              chunksIndexed: parsed.chunks_indexed,
              bytesIndexed: parsed.bytes_indexed,
              message: parsed.message,
              finished: ev.event === "done" || ev.event === "error",
            });
            if (ev.event === "done" || ev.event === "error") break;
          } catch {
            // ignore bad payload
          }
        }
      } catch {
        // connection torn down — UI will fall back to polled state
      }
    })();

    return () => {
      ctrl.abort();
      reset(job.id);
    };
  }, [repoId, job.id, job.status, update, reset]);

  const filesSeen = progress?.filesSeen ?? job.files_seen;
  const filesIndexed = progress?.filesIndexed ?? job.files_indexed;
  const chunksIndexed = progress?.chunksIndexed ?? job.chunks_indexed;

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-2">
      <div className="text-sm font-medium">Active ingest</div>
      <div className="grid grid-cols-3 gap-3 text-sm">
        <Stat label="Files seen" value={filesSeen} />
        <Stat label="Files indexed" value={filesIndexed} />
        <Stat label="Chunks indexed" value={chunksIndexed} />
      </div>
      {progress?.message ? (
        <div className="text-xs text-muted-foreground">{progress.message}</div>
      ) : null}
    </section>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded border border-border p-2">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="font-mono text-lg">{value}</div>
    </div>
  );
}
