import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useParams, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import { api, type CodeChunkPreview, type IngestJob, type RepositoryFile } from "@/lib/api";
import { readSse } from "@/lib/sse";
import { useReposStore } from "@/stores/repos-store";
import { useAuthStore } from "@/stores/auth-store";

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
            <JobRow key={j.id} job={j} />
          ))}
        </div>
      </section>

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
    <div className="rounded border border-border bg-card p-3 text-sm">
      <div className="flex justify-between items-center">
        <span
          className={
            "text-xs rounded px-2 py-0.5 " + JOB_STATUS_COLORS[job.status]
          }
        >
          {job.status}
        </span>
        <code className="text-xs text-muted-foreground">{job.id.slice(0, 8)}</code>
      </div>
      <div className="text-xs text-muted-foreground mt-1">
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
            <pre className="mt-1 text-xs text-destructive whitespace-pre-wrap break-words font-mono bg-destructive/5 rounded p-2 max-h-48 overflow-auto">
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
        <div className="text-sm text-muted-foreground">
          No indexed files yet. Run an ingest first.
        </div>
      ) : (
        <div className="rounded border border-border bg-card overflow-hidden">
          <table className="w-full text-sm">
            <thead className="bg-muted/30">
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
                  className={
                    "border-t border-border cursor-pointer hover:bg-muted/20 " +
                    (selectedFile?.id === f.id ? "bg-muted/30" : "")
                  }
                >
                  <td className="px-3 py-2 font-mono text-xs break-all">{f.path}</td>
                  <td className="px-3 py-2 text-xs text-muted-foreground">
                    {f.language ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">
                    {formatBytes(f.size_bytes)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">{f.lines}</td>
                  <td className="px-3 py-2 text-right tabular-nums text-xs">{f.chunk_count}</td>
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
      className={
        "px-3 py-2 text-xs font-medium text-muted-foreground select-none " +
        (onClick ? "cursor-pointer hover:text-foreground " : "") +
        (className ?? "")
      }
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

  return (
    <div className="rounded-lg border border-border bg-card p-4 space-y-3">
      <div className="flex justify-between items-start gap-3">
        <div>
          <div className="text-sm font-medium font-mono break-all">{file.path}</div>
          <div className="text-xs text-muted-foreground">
            {file.language ?? "unknown"} · {formatBytes(file.size_bytes)} · {file.lines} lines ·{" "}
            {file.chunk_count} chunk{file.chunk_count === 1 ? "" : "s"}
          </div>
        </div>
        <button
          onClick={onClose}
          className="text-xs text-muted-foreground hover:text-foreground"
        >
          Close ✕
        </button>
      </div>

      {isLoading ? (
        <div className="text-sm text-muted-foreground">Loading chunks…</div>
      ) : (chunks ?? []).length === 0 ? (
        <div className="text-sm text-muted-foreground">No chunks for this file.</div>
      ) : (
        <div className="space-y-3">
          {chunks!.map((c: CodeChunkPreview, idx) => (
            <div key={c.id} className="rounded border border-border overflow-hidden">
              <div className="flex justify-between items-center px-2 py-1 bg-muted/30 text-xs text-muted-foreground">
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

function formatBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}
