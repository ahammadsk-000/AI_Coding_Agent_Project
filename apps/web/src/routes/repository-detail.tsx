import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, GitBranch, GitCompare, X } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import { api, type CodeChunkPreview, type IngestJob, type RepositoryFile } from "@/lib/api";
import { InsightsSection } from "@/components/repo/insights-section";
import { AuditSection } from "@/components/repo/audit-section";
import { MetricsPanel } from "@/components/repo/metrics-panel";
import { readSse } from "@/lib/sse";
import { useReposStore } from "@/stores/repos-store";
import { useAuthStore } from "@/stores/auth-store";
import { cn } from "@/lib/utils";

// Map our internal language tags (from app.infrastructure.parsers.language) to
// the language ids Prism recognizes. Unknown tags fall back to plaintext.
const PRISM_LANG_MAP: Record<string, string> = {
  python: "python",
  typescript: "typescript",
  javascript: "javascript",
  go: "go",
  rust: "rust",
  java: "java",
  cpp: "cpp",
  c: "c",
  kotlin: "kotlin",
  csharp: "csharp",
  ruby: "ruby",
  php: "php",
  swift: "swift",
  scala: "scala",
  html: "markup",
  xml: "markup",
  css: "css",
  scss: "scss",
  less: "less",
  markdown: "markdown",
  restructuredtext: "markdown",
  json: "json",
  yaml: "yaml",
  toml: "toml",
  sql: "sql",
  bash: "bash",
  dockerfile: "docker",
  make: "makefile",
  cmake: "cmake",
  ini: "ini",
  dotenv: "bash",
  text: "plaintext",
};

function prismLanguage(language: string | null | undefined): string {
  if (!language) return "plaintext";
  return PRISM_LANG_MAP[language] ?? "plaintext";
}

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
    <div className="max-w-5xl space-y-6">
      <Link
        to="/repositories"
        className="inline-flex items-center gap-1 text-sm text-muted-foreground transition-colors hover:text-foreground"
      >
        <ArrowLeft className="h-4 w-4" /> All repositories
      </Link>
      <header className="flex items-center gap-2.5">
        <div className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-gradient-to-br from-sky-400 to-cyan-500 shadow-md">
          <GitBranch className="h-5 w-5 text-white" />
        </div>
        <div className="min-w-0">
          <h1 className="truncate text-2xl font-semibold tracking-tight">{repo?.name ?? "…"}</h1>
          <div className="truncate text-xs text-muted-foreground">{repo?.url}</div>
        </div>
      </header>

      {currentJob ? <JobPanel repoId={repoId} job={currentJob} /> : null}

      <section className="space-y-2">
        <h2 className="text-sm font-medium">Recent jobs</h2>
        <div className="space-y-2">
          {(jobs ?? []).map((j) => (
            <JobRow key={j.id} job={j} />
          ))}
        </div>
      </section>

      <MetricsPanel repoId={repoId} />

      <InsightsSection repoId={repoId} />

      <AuditSection repoId={repoId} />

      <FilesSection repoId={repoId} />
    </div>
  );
}

function JobPanel({ repoId, job }: { repoId: string; job: IngestJob }) {
  const progress = useReposStore((s) => s.progressByJobId[job.id]);
  const update = useReposStore((s) => s.updateProgress);
  const reset = useReposStore((s) => s.reset);
  const [, setBeat] = useState(0);

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
    <section className="space-y-3 rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <div className="flex items-center gap-2 text-sm font-medium">
        <span className="h-2 w-2 animate-pulse rounded-full bg-amber-500" />
        Active ingest
      </div>
      <div className="grid grid-cols-3 gap-3">
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
    <div className="rounded-lg border border-border bg-card/40 p-3">
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-2xl font-semibold tabular-nums">{value}</div>
    </div>
  );
}

const JOB_STATUS_COLORS: Record<IngestJob["status"], string> = {
  queued: "bg-muted text-muted-foreground",
  running: "bg-amber-500/15 text-amber-500",
  succeeded: "bg-emerald-500/15 text-emerald-500",
  failed: "bg-destructive/15 text-destructive",
  canceled: "bg-muted text-muted-foreground",
};

function JobRow({ job }: { job: IngestJob }) {
  const [showError, setShowError] = useState(false);
  const hasError = job.status === "failed" && !!job.error;

  return (
    <div className="rounded-xl border border-border bg-card/60 p-3.5 text-sm backdrop-blur">
      <div className="flex items-center justify-between">
        <span className={cn("rounded-full px-2 py-0.5 text-xs capitalize", JOB_STATUS_COLORS[job.status])}>
          {job.status}
        </span>
        <code className="text-xs text-muted-foreground">{job.id.slice(0, 8)}</code>
      </div>
      <div className="mt-1.5 text-xs text-muted-foreground">
        files: {job.files_indexed}/{job.files_seen} · chunks: {job.chunks_indexed}
      </div>
      {hasError ? (
        <div className="mt-2">
          <button
            onClick={() => setShowError((v) => !v)}
            className="text-xs text-destructive hover:underline"
          >
            {showError ? "Hide error ▴" : "Show error ▾"}
          </button>
          {showError ? (
            <pre className="mt-1 max-h-48 overflow-auto whitespace-pre-wrap break-words rounded-md bg-destructive/5 p-2 font-mono text-xs text-destructive">
              {job.error}
            </pre>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

// -------- files + chunk preview --------

type SortKey = "path" | "language" | "size_bytes" | "lines" | "chunk_count";

function FilesSection({ repoId }: { repoId: string }) {
  const { data: files, isLoading } = useQuery({
    queryKey: ["repo-files", repoId],
    queryFn: () => api.listFiles(repoId),
    refetchInterval: 5000,
  });

  const [sortKey, setSortKey] = useState<SortKey>("path");
  const [sortDir, setSortDir] = useState<"asc" | "desc">("asc");
  const [selectedFile, setSelectedFile] = useState<RepositoryFile | null>(null);

  const sortedFiles = useMemo(() => {
    if (!files) return [];
    const copy = [...files];
    copy.sort((a, b) => {
      const av = a[sortKey] ?? "";
      const bv = b[sortKey] ?? "";
      if (typeof av === "number" && typeof bv === "number") {
        return sortDir === "asc" ? av - bv : bv - av;
      }
      const as = String(av);
      const bs = String(bv);
      return sortDir === "asc" ? as.localeCompare(bs) : bs.localeCompare(as);
    });
    return copy;
  }, [files, sortKey, sortDir]);

  function toggleSort(key: SortKey) {
    if (sortKey === key) {
      setSortDir((d) => (d === "asc" ? "desc" : "asc"));
    } else {
      setSortKey(key);
      setSortDir("asc");
    }
  }

  const arrow = (key: SortKey) =>
    sortKey === key ? (sortDir === "asc" ? " ▲" : " ▼") : "";

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium">Files ({files?.length ?? 0})</h2>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading…</div>
      ) : sortedFiles.length === 0 ? (
        <div className="rounded-xl border border-border bg-card/40 p-8 text-center text-sm text-muted-foreground">
          No indexed files yet. Run an ingest first.
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-border bg-card/60 backdrop-blur">
          <table className="w-full text-sm">
            <thead className="bg-muted/20">
              <tr className="text-left">
                <Th onClick={() => toggleSort("path")}>Path{arrow("path")}</Th>
                <Th onClick={() => toggleSort("language")}>Language{arrow("language")}</Th>
                <Th onClick={() => toggleSort("size_bytes")} className="text-right">
                  Size{arrow("size_bytes")}
                </Th>
                <Th onClick={() => toggleSort("lines")} className="text-right">
                  Lines{arrow("lines")}
                </Th>
                <Th onClick={() => toggleSort("chunk_count")} className="text-right">
                  Chunks{arrow("chunk_count")}
                </Th>
              </tr>
            </thead>
            <tbody>
              {sortedFiles.map((f) => (
                <tr
                  key={f.id}
                  onClick={() => setSelectedFile(f)}
                  className={cn(
                    "cursor-pointer border-t border-border transition-colors hover:bg-muted/20",
                    selectedFile?.id === f.id && "bg-primary/5",
                  )}
                >
                  <td className="break-all px-3 py-2 font-mono text-xs">{f.path}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {f.language ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right text-xs tabular-nums">
                    {formatBytes(f.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right text-xs tabular-nums">{f.lines}</td>
                  <td className="px-3 py-2 text-right text-xs tabular-nums">{f.chunk_count}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {selectedFile ? (
        <ChunkPreview
          repoId={repoId}
          file={selectedFile}
          onClose={() => setSelectedFile(null)}
        />
      ) : null}
    </section>
  );
}

function Th({
  children,
  onClick,
  className,
}: {
  children: ReactNode;
  onClick?: () => void;
  className?: string;
}) {
  return (
    <th
      onClick={onClick}
      className={cn(
        "select-none px-3 py-2 text-xs font-medium text-muted-foreground",
        onClick && "cursor-pointer hover:text-foreground",
        className,
      )}
    >
      {children}
    </th>
  );
}

function ChunkPreview({
  repoId,
  file,
  onClose,
}: {
  repoId: string;
  file: RepositoryFile;
  onClose: () => void;
}) {
  const { data: chunks, isLoading } = useQuery({
    queryKey: ["chunks", repoId, file.id],
    queryFn: () => api.listFileChunks(repoId, file.id),
  });
  const [showSimilar, setShowSimilar] = useState(false);

  return (
    <div className="space-y-3 rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="break-all font-mono text-sm font-medium">{file.path}</div>
          <div className="text-xs text-muted-foreground">
            {file.language ?? "unknown"} · {formatBytes(file.size_bytes)} · {file.lines} lines ·{" "}
            {file.chunk_count} chunk{file.chunk_count === 1 ? "" : "s"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="shrink-0 rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          title="Close"
        >
          <X className="h-4 w-4" />
        </button>
      </div>

      <div className="space-y-2">
        <button
          onClick={() => setShowSimilar((v) => !v)}
          className="inline-flex items-center gap-1 rounded-md border border-border px-2 py-1 text-xs text-muted-foreground transition-colors hover:text-foreground"
        >
          <GitCompare className="h-3.5 w-3.5" />
          {showSimilar ? "Hide similar code" : "Find similar code"}
        </button>
        {showSimilar ? <SimilarMatches repoId={repoId} fileId={file.id} /> : null}
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading chunks…</div>
      ) : (chunks ?? []).length === 0 ? (
        <div className="text-sm text-muted-foreground">No chunks for this file.</div>
      ) : (
        <div className="space-y-3">
          {chunks!.map((c: CodeChunkPreview, idx) => (
            <div key={c.id} className="overflow-hidden rounded-lg border border-border">
              <div className="flex items-center justify-between bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
                <span>
                  Chunk #{idx + 1} · lines {c.start_line}–{c.end_line}
                </span>
                <span className="tabular-nums">{c.token_count} tokens</span>
              </div>
              <SyntaxHighlighter
                language={prismLanguage(c.language ?? file.language)}
                style={vscDarkPlus}
                showLineNumbers
                startingLineNumber={c.start_line}
                wrapLongLines
                customStyle={{
                  margin: 0,
                  fontSize: "0.75rem",
                  background: "rgb(30, 30, 30)",
                }}
                codeTagProps={{ style: { fontFamily: "ui-monospace, monospace" } }}
              >
                {c.content}
              </SyntaxHighlighter>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function SimilarMatches({ repoId, fileId }: { repoId: string; fileId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["similar", repoId, fileId],
    queryFn: () => api.repoSimilar(repoId, fileId),
  });

  if (isLoading)
    return <div className="text-xs text-muted-foreground">Finding similar code…</div>;
  if (isError)
    return <div className="text-xs text-destructive">Could not search for similar code.</div>;

  const matches = data?.matches ?? [];
  if (matches.length === 0)
    return (
      <div className="text-xs text-muted-foreground">
        No semantically similar code found elsewhere in this repo.
      </div>
    );

  return (
    <div className="space-y-1.5">
      <div className="text-xs text-muted-foreground">
        Nearest matches elsewhere in the repo (possible duplication / refactor candidates):
      </div>
      {matches.map((m, i) => (
        <div
          key={`${m.file_id}-${i}`}
          className="flex items-center justify-between gap-2 rounded-lg border border-border bg-card/40 px-2.5 py-1.5"
        >
          <span className="truncate font-mono text-xs" title={m.file_path}>
            {m.file_path}
            <span className="text-muted-foreground">
              :{m.start_line}-{m.end_line}
            </span>
          </span>
          <span className="shrink-0 rounded-full bg-primary/10 px-2 py-0.5 text-xs font-medium tabular-nums text-primary">
            {Math.round(m.score * 100)}% match
          </span>
        </div>
      ))}
    </div>
  );
}

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
