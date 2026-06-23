import { useQuery } from "@tanstack/react-query";
import { BarChart3, FileCode2, FlaskConical, Hash } from "lucide-react";

import { api } from "@/lib/api";

// A small, stable palette for language bars (cycles if there are more langs).
const LANG_COLORS = [
  "#60a5fa", // blue
  "#34d399", // emerald
  "#fbbf24", // amber
  "#f472b6", // pink
  "#a78bfa", // violet
  "#22d3ee", // cyan
  "#fb7185", // rose
  "#a3e635", // lime
  "#94a3b8", // slate (other)
];

function fmtNum(n: number): string {
  return n.toLocaleString();
}

function fmtBytes(n: number): string {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

export function MetricsPanel({ repoId }: { repoId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["repo-metrics", repoId],
    queryFn: () => api.repoMetrics(repoId),
  });

  if (isLoading || !data || data.total_files === 0) return null;

  const totalLines = data.total_lines || 1;
  const langs = data.languages.slice(0, 8);
  const maxFileLines = data.largest_files[0]?.lines || 1;
  const testPct = Math.round((data.test_files / data.total_files) * 100);

  return (
    <section className="space-y-3">
      <h2 className="flex items-center gap-1.5 text-sm font-medium">
        <BarChart3 className="h-4 w-4 text-muted-foreground" /> Metrics
      </h2>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard icon={<FileCode2 className="h-4 w-4" />} label="Files" value={fmtNum(data.total_files)} />
        <StatCard icon={<Hash className="h-4 w-4" />} label="Lines of code" value={fmtNum(data.total_lines)} />
        <StatCard icon={<BarChart3 className="h-4 w-4" />} label="Total size" value={fmtBytes(data.total_bytes)} />
        <StatCard
          icon={<FlaskConical className="h-4 w-4" />}
          label="Test files"
          value={`${fmtNum(data.test_files)} · ${testPct}%`}
        />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        {/* language breakdown */}
        <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
          <div className="mb-3 text-sm font-medium">Languages</div>
          <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-muted/40">
            {langs.map((l, i) => (
              <div
                key={l.language}
                style={{
                  width: `${(l.lines / totalLines) * 100}%`,
                  backgroundColor: LANG_COLORS[i % LANG_COLORS.length],
                }}
                title={`${l.language}: ${fmtNum(l.lines)} lines`}
              />
            ))}
          </div>
          <ul className="mt-3 space-y-1.5">
            {langs.map((l, i) => (
              <li key={l.language} className="flex items-center justify-between text-xs">
                <span className="flex items-center gap-1.5">
                  <span
                    className="h-2.5 w-2.5 rounded-sm"
                    style={{ backgroundColor: LANG_COLORS[i % LANG_COLORS.length] }}
                  />
                  <span className="text-foreground">{l.language}</span>
                  <span className="text-muted-foreground">· {l.files} file{l.files === 1 ? "" : "s"}</span>
                </span>
                <span className="tabular-nums text-muted-foreground">
                  {Math.round((l.lines / totalLines) * 100)}%
                </span>
              </li>
            ))}
          </ul>
        </div>

        {/* largest files */}
        <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
          <div className="mb-3 text-sm font-medium">Largest files</div>
          <ul className="space-y-2">
            {data.largest_files.slice(0, 8).map((f) => (
              <li key={f.path} className="space-y-1">
                <div className="flex items-center justify-between gap-2 text-xs">
                  <span className="truncate font-mono text-muted-foreground" title={f.path}>
                    {f.path}
                  </span>
                  <span className="shrink-0 tabular-nums text-muted-foreground">
                    {fmtNum(f.lines)} ln
                  </span>
                </div>
                <div className="h-1.5 w-full overflow-hidden rounded-full bg-muted/40">
                  <div
                    className="h-full rounded-full bg-gradient-to-r from-sky-400 to-cyan-500"
                    style={{ width: `${(f.lines / maxFileLines) * 100}%` }}
                  />
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </section>
  );
}

function StatCard({
  icon,
  label,
  value,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
}) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-3 backdrop-blur">
      <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
        {icon}
        {label}
      </div>
      <div className="mt-1 font-mono text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
