import { useRef, useState } from "react";
import { ShieldAlert, Play, Square, AlertTriangle, Bug, Lock, Gauge, Sparkles } from "lucide-react";

import { Button } from "@/components/ui/button";
import { readSse } from "@/lib/sse";
import { cn } from "@/lib/utils";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

const MODELS = [
  { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B · fast (recommended)" },
  { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · quality" },
];

interface Finding {
  severity: "high" | "medium" | "low";
  category: "bug" | "security" | "smell" | "perf";
  line: number | null;
  title: string;
  detail: string;
}

interface FileResult {
  path: string;
  findings: Finding[];
  error?: string | null;
}

interface Summary {
  total: number;
  by_severity: { high: number; medium: number; low: number };
  by_category: Record<string, number>;
}

export function AuditSection({ repoId }: { repoId: string }) {
  const [depth, setDepth] = useState(6);
  const [model, setModel] = useState(MODELS[0]!.id);
  const [running, setRunning] = useState(false);
  const [planned, setPlanned] = useState<string[]>([]);
  const [results, setResults] = useState<FileResult[]>([]);
  const [summary, setSummary] = useState<Summary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function stop() {
    abortRef.current?.abort();
  }

  async function run() {
    if (running) return;
    setError(null);
    setPlanned([]);
    setResults([]);
    setSummary(null);
    setRunning(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const params = new URLSearchParams({
      repository_id: repoId,
      depth: String(depth),
      model,
    });
    const url = `${BASE_URL}/api/v1/audit/run/stream?${params.toString()}`;

    try {
      for await (const ev of readSse(url, { signal: ctrl.signal })) {
        const data = JSON.parse(ev.data);
        if (ev.event === "start") setPlanned(data.files ?? []);
        else if (ev.event === "file")
          setResults((p) => [
            ...p,
            { path: data.path, findings: data.findings ?? [], error: data.error ?? null },
          ]);
        else if (ev.event === "summary") setSummary(data);
        else if (ev.event === "error") setError(data.message ?? "Audit failed");
      }
    } catch (err) {
      if (!ctrl.signal.aborted)
        setError(err instanceof Error ? err.message : "audit stream failed");
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  const started = planned.length > 0 || results.length > 0;

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-1.5 text-sm font-medium">
        <ShieldAlert className="h-4 w-4 text-muted-foreground" /> Security &amp; quality audit
      </h2>
      <div className="rounded-xl border border-border bg-card/50 p-4 backdrop-blur">
        <p className="mb-3 text-xs text-muted-foreground">
          A reviewer agent scans your most substantial files for bugs, security
          issues, and smells — streamed file-by-file. Token-intensive; scoped by depth.
        </p>
        <div className="flex flex-wrap items-center gap-3 text-xs">
          <label className="flex items-center gap-1.5 text-muted-foreground">
            Files
            <select
              value={depth}
              onChange={(e) => setDepth(Number(e.target.value))}
              className="rounded-md border border-border bg-card/60 px-2 py-1.5 focus:outline-none focus:ring-1 focus:ring-ring"
            >
              {[3, 6, 9, 12].map((n) => (
                <option key={n} value={n}>
                  top {n}
                </option>
              ))}
            </select>
          </label>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            className="rounded-md border border-border bg-card/60 px-2 py-1.5 text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
          <div className="flex items-center gap-2">
            <Button
              type="button"
              size="sm"
              loading={running}
              onClick={run}
              className="bg-gradient-to-r from-rose-500 to-orange-500"
            >
              <Play className="mr-1 h-4 w-4" /> Run audit
            </Button>
            {running ? (
              <Button type="button" size="sm" variant="outline" onClick={stop}>
                <Square className="mr-1 h-4 w-4" /> Stop
              </Button>
            ) : null}
          </div>
        </div>
        {error ? <div className="mt-3 text-sm text-destructive">{error}</div> : null}
      </div>

      {summary ? <SummaryCard summary={summary} /> : null}

      {started ? (
        <div className="space-y-3">
          {results.map((r) => (
            <FileCard key={r.path} result={r} />
          ))}
          {running && results.length < planned.length ? (
            <div className="px-1 text-xs text-muted-foreground">
              reviewing {results.length + 1} / {planned.length}:{" "}
              <span className="font-mono">{planned[results.length]}</span>…
            </div>
          ) : null}
          {!running && summary && summary.total === 0 ? (
            <div className="flex items-center gap-1.5 rounded-xl border border-border bg-card/40 p-4 text-sm text-emerald-400">
              <Sparkles className="h-4 w-4" /> No issues found in the reviewed files. Clean!
            </div>
          ) : null}
        </div>
      ) : null}
    </section>
  );
}

function SummaryCard({ summary }: { summary: Summary }) {
  return (
    <div className="flex flex-wrap items-center gap-3 rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <span className="text-sm font-medium">
        {summary.total} finding{summary.total === 1 ? "" : "s"}
      </span>
      <SevPill sev="high" n={summary.by_severity.high} />
      <SevPill sev="medium" n={summary.by_severity.medium} />
      <SevPill sev="low" n={summary.by_severity.low} />
    </div>
  );
}

const SEV_STYLES: Record<string, string> = {
  high: "bg-destructive/15 text-destructive",
  medium: "bg-amber-500/15 text-amber-500",
  low: "bg-sky-500/15 text-sky-400",
};

function SevPill({ sev, n }: { sev: "high" | "medium" | "low"; n: number }) {
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium capitalize tabular-nums",
        SEV_STYLES[sev],
      )}
    >
      {n} {sev}
    </span>
  );
}

const CAT_ICON: Record<string, React.ReactNode> = {
  bug: <Bug className="h-3.5 w-3.5" />,
  security: <Lock className="h-3.5 w-3.5" />,
  perf: <Gauge className="h-3.5 w-3.5" />,
  smell: <AlertTriangle className="h-3.5 w-3.5" />,
};

function FileCard({ result }: { result: FileResult }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <div className="mb-2 flex items-center justify-between gap-2">
        <span className="truncate font-mono text-xs font-medium" title={result.path}>
          {result.path}
        </span>
        <span className="shrink-0 text-xs text-muted-foreground">
          {result.error ? "error" : `${result.findings.length} finding${result.findings.length === 1 ? "" : "s"}`}
        </span>
      </div>
      {result.error ? (
        <div className="text-xs text-destructive">{result.error}</div>
      ) : result.findings.length === 0 ? (
        <div className="text-xs text-muted-foreground">No issues found.</div>
      ) : (
        <ul className="space-y-2">
          {result.findings.map((f, i) => (
            <li key={i} className="rounded-lg border border-border bg-card/40 p-2.5">
              <div className="flex flex-wrap items-center gap-2">
                <span
                  className={cn(
                    "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
                    SEV_STYLES[f.severity],
                  )}
                >
                  {f.severity}
                </span>
                <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                  {CAT_ICON[f.category]}
                  {f.category}
                </span>
                {f.line != null ? (
                  <span className="font-mono text-xs text-muted-foreground">line {f.line}</span>
                ) : null}
                <span className="text-sm font-medium">{f.title}</span>
              </div>
              {f.detail ? (
                <p className="mt-1 text-sm text-muted-foreground">{f.detail}</p>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
