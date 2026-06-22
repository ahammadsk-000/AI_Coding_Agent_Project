import { useState, type FormEvent, type ReactNode } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Workflow, Compass, Search as SearchIcon, Sparkles, Play } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { api, ApiError, type AgentRunResponse } from "@/lib/api";
import { cn } from "@/lib/utils";

const MODELS = [
  { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B · fast (recommended)" },
  { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · quality" },
];

export function AgentsPage() {
  const { data: repos } = useQuery({ queryKey: ["repos"], queryFn: api.listRepos });
  const ready = (repos ?? []).filter((r) => r.status === "ready");

  const [task, setTask] = useState("");
  const [model, setModel] = useState(MODELS[0]!.id);
  const [scope, setScope] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const run = useMutation({
    mutationFn: () =>
      api.runAgents({ task, repository_ids: scope, model, max_steps: 3 }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Agent run failed"),
    onSuccess: () => setError(null),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!task.trim()) return;
    run.mutate();
  }

  function toggle(id: string) {
    setScope((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  return (
    <div className="max-w-4xl space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-violet-500 to-fuchsia-500 shadow-md">
            <Workflow className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Agents</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          A multi-agent pipeline: a <strong>planner</strong> breaks your task into
          sub-questions, <strong>researcher</strong> agents answer each from your
          code, and a <strong>synthesizer</strong> combines them. Token-intensive
          (several LLM calls) — uses the model selected below.
        </p>
      </header>

      <form
        onSubmit={submit}
        className="space-y-3 rounded-xl border border-border bg-card/50 p-4 backdrop-blur"
      >
        <textarea
          value={task}
          onChange={(e) => setTask(e.target.value)}
          rows={3}
          placeholder="e.g. How does click implement command groups and option parsing? Summarize the architecture."
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
          loading={run.isPending}
          className="bg-gradient-to-r from-violet-500 to-fuchsia-500"
        >
          <Play className="mr-1 h-4 w-4" /> Run agents
        </Button>
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
        {run.isPending ? (
          <div className="text-xs text-muted-foreground">
            Planning → researching → synthesizing… (several LLM calls, ~15–30s)
          </div>
        ) : null}
      </form>

      {run.data ? <AgentResult result={run.data} /> : null}
    </div>
  );
}

function AgentResult({ result }: { result: AgentRunResponse }) {
  return (
    <div className="space-y-4">
      <Stage
        icon={<Compass className="h-4 w-4" />}
        title="Planner"
        subtitle={`${result.plan.length} sub-question(s)`}
        grad="from-sky-400 to-indigo-500"
      >
        <ol className="ml-4 list-decimal space-y-1 text-sm">
          {result.plan.map((p, i) => (
            <li key={i}>{p}</li>
          ))}
        </ol>
      </Stage>

      {result.steps.map((s, i) => (
        <Stage
          key={i}
          icon={<SearchIcon className="h-4 w-4" />}
          title={`Researcher ${i + 1}`}
          subtitle={s.title}
          grad="from-emerald-400 to-teal-500"
        >
          {s.error ? (
            <div className="text-sm text-destructive">error: {s.error}</div>
          ) : (
            <>
              <Markdown content={s.finding} />
              {s.citations.length ? (
                <div className="mt-2 flex flex-wrap gap-1.5">
                  {s.citations.slice(0, 8).map((c, j) => (
                    <span
                      key={j}
                      className="rounded-md border border-border bg-card/60 px-2 py-0.5 font-mono text-xs text-muted-foreground"
                    >
                      {c.file_path}:{c.start_line}-{c.end_line}
                    </span>
                  ))}
                </div>
              ) : null}
            </>
          )}
        </Stage>
      ))}

      <Stage
        icon={<Sparkles className="h-4 w-4" />}
        title="Synthesizer"
        subtitle="Final answer"
        grad="from-violet-500 to-fuchsia-500"
      >
        <Markdown content={result.synthesis} />
      </Stage>
      <div className="text-xs text-muted-foreground">model: {result.model}</div>
    </div>
  );
}

function Stage({
  icon,
  title,
  subtitle,
  grad,
  children,
}: {
  icon: ReactNode;
  title: string;
  subtitle?: string;
  grad: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <div className="mb-2.5 flex items-center gap-2.5">
        <div
          className={cn(
            "grid h-8 w-8 shrink-0 place-items-center rounded-lg bg-gradient-to-br text-white shadow-md",
            grad,
          )}
        >
          {icon}
        </div>
        <div className="min-w-0">
          <div className="text-sm font-medium">{title}</div>
          {subtitle ? (
            <div className="truncate text-xs text-muted-foreground">{subtitle}</div>
          ) : null}
        </div>
      </div>
      {children}
    </div>
  );
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words prose-p:my-1.5">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
