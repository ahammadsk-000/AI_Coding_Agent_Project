import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { FlaskConical, Play, ShieldCheck, Target, Crosshair } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { api, ApiError, type RagMetric } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODELS = [
  { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B · fast (recommended)" },
  { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · quality" },
];

const METRIC_META: Record<string, { label: string; icon: React.ReactNode; blurb: string }> = {
  faithfulness: {
    label: "Faithfulness",
    icon: <ShieldCheck className="h-4 w-4" />,
    blurb: "Are the answer's claims grounded in the retrieved code? (anti-hallucination)",
  },
  answer_relevance: {
    label: "Answer relevance",
    icon: <Target className="h-4 w-4" />,
    blurb: "Does the answer actually address the question?",
  },
  context_precision: {
    label: "Context precision",
    icon: <Crosshair className="h-4 w-4" />,
    blurb: "Is the retrieved context relevant to the question?",
  },
};

export function EvalPage() {
  const { data: repos } = useQuery({ queryKey: ["repos"], queryFn: api.listRepos });
  const ready = (repos ?? []).filter((r) => r.status === "ready");

  const [query, setQuery] = useState("");
  const [model, setModel] = useState(MODELS[0]!.id);
  const [scope, setScope] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const evalMut = useMutation({
    mutationFn: () => api.evalRag({ query, repository_ids: scope, model }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "evaluation failed"),
    onSuccess: () => setError(null),
  });
  const result = evalMut.data;

  function toggle(id: string) {
    setScope((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!query.trim() || evalMut.isPending) return;
    setError(null);
    evalMut.mutate();
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-teal-500 to-emerald-500 shadow-md">
            <FlaskConical className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">RAG Evaluation</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Runs the real retrieval + generation pipeline for a question, then scores it with an{" "}
          <strong>LLM-as-judge</strong> on the RAGAS-style metrics —{" "}
          <strong>faithfulness</strong>, <strong>answer relevance</strong>, and{" "}
          <strong>context precision</strong>. Reference-free (no labels needed). Token-intensive.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="space-y-3 rounded-xl border border-border bg-card/50 p-4 backdrop-blur"
      >
        <textarea
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          rows={2}
          placeholder="e.g. How does click parse command-line options?"
          className="w-full resize-none rounded-md border border-border bg-card/60 px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-ring"
        />
        <div className="flex flex-wrap items-center gap-3 text-xs">
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
          {ready.length ? (
            <div className="flex flex-wrap gap-1.5">
              {ready.map((r) => (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => toggle(r.id)}
                  className={cn(
                    "rounded-full border px-2.5 py-0.5 transition-colors",
                    scope.includes(r.id)
                      ? "border-primary/30 bg-primary/15 text-primary"
                      : "border-border text-muted-foreground hover:text-foreground",
                  )}
                >
                  {r.name}
                </button>
              ))}
            </div>
          ) : null}
        </div>
        <Button
          type="submit"
          loading={evalMut.isPending}
          className="bg-gradient-to-r from-teal-500 to-emerald-500"
        >
          <Play className="mr-1 h-4 w-4" /> Run evaluation
        </Button>
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
      </form>

      {result ? (
        result.note ? (
          <div className="rounded-xl border border-border bg-card/40 p-4 text-sm text-muted-foreground">
            {result.note}
          </div>
        ) : (
          <div className="space-y-4">
            {/* scores */}
            <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
              <div className="mb-3 flex items-center justify-between">
                <span className="text-sm font-medium">Scores</span>
                <span className="text-xs text-muted-foreground">
                  {result.retrieved} chunks · {result.reranked ? "reranked · " : ""}
                  {result.took_ms}ms retrieval · {result.model}
                </span>
              </div>
              {typeof result.overall === "number" ? (
                <div className="mb-4 flex items-center gap-3">
                  <span className="text-sm text-muted-foreground">Overall</span>
                  <ScoreBar score={result.overall} big />
                </div>
              ) : null}
              <div className="grid gap-3 sm:grid-cols-3">
                {Object.entries(result.metrics).map(([key, m]) => (
                  <MetricCard key={key} metricKey={key} metric={m} />
                ))}
              </div>
            </div>

            {/* answer */}
            <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
              <div className="mb-2 text-sm font-medium">Generated answer</div>
              <div className="prose prose-invert prose-sm max-w-none break-words">
                <ReactMarkdown remarkPlugins={[remarkGfm]}>{result.answer}</ReactMarkdown>
              </div>
            </div>

            {/* retrieved context */}
            <details className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
              <summary className="cursor-pointer text-sm font-medium">
                Retrieved context ({result.contexts.length})
              </summary>
              <div className="mt-3 space-y-2">
                {result.contexts.map((c, i) => (
                  <div key={i} className="rounded-lg border border-border bg-card/40 p-2">
                    <div className="mb-1 font-mono text-xs text-muted-foreground">
                      {c.file_path}:{c.start_line}-{c.end_line}
                    </div>
                    <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words text-xs">
                      {c.content}
                    </pre>
                  </div>
                ))}
              </div>
            </details>
          </div>
        )
      ) : null}
    </div>
  );
}

function MetricCard({ metricKey, metric }: { metricKey: string; metric: RagMetric }) {
  const meta = METRIC_META[metricKey] ?? {
    label: metricKey,
    icon: <FlaskConical className="h-4 w-4" />,
    blurb: "",
  };
  return (
    <div className="rounded-lg border border-border bg-card/40 p-3">
      <div className="flex items-center gap-1.5 text-sm font-medium">
        <span className="text-muted-foreground">{meta.icon}</span>
        {meta.label}
      </div>
      <div className="my-2">
        <ScoreBar score={metric.score} />
      </div>
      <p className="text-xs text-muted-foreground">{metric.reason}</p>
    </div>
  );
}

function ScoreBar({ score, big = false }: { score: number; big?: boolean }) {
  const pct = Math.round(score * 100);
  const color =
    score >= 0.75 ? "bg-emerald-500" : score >= 0.5 ? "bg-amber-500" : "bg-destructive";
  return (
    <div className={cn("flex items-center gap-2", big && "flex-1")}>
      <div className={cn("w-full overflow-hidden rounded-full bg-muted/40", big ? "h-2.5" : "h-2")}>
        <div className={cn("h-full rounded-full", color)} style={{ width: `${pct}%` }} />
      </div>
      <span className={cn("shrink-0 tabular-nums", big ? "text-sm font-semibold" : "text-xs")}>
        {score.toFixed(2)}
      </span>
    </div>
  );
}
