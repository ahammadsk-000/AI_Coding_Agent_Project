import { useMemo, useRef, useState, type FormEvent, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Workflow,
  Compass,
  Search as SearchIcon,
  Sparkles,
  Play,
  Square,
  ShieldCheck,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { api, type AgentStep, type AgentReview } from "@/lib/api";
import { readSse } from "@/lib/sse";
import { cn } from "@/lib/utils";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://localhost:8000";

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
  const [review, setReview] = useState(true);

  const [running, setRunning] = useState(false);
  const [plan, setPlan] = useState<string[]>([]);
  const [steps, setSteps] = useState<AgentStep[]>([]);
  const [synthesis, setSynthesis] = useState("");
  const [critic, setCritic] = useState<AgentReview | null>(null);
  const [refined, setRefined] = useState(false);
  const [refining, setRefining] = useState(false);
  const [modelUsed, setModelUsed] = useState("");
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  function toggle(id: string) {
    setScope((p) => (p.includes(id) ? p.filter((x) => x !== id) : [...p, id]));
  }

  function stop() {
    abortRef.current?.abort();
  }

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!task.trim() || running) return;
    setError(null);
    setPlan([]);
    setSteps([]);
    setSynthesis("");
    setCritic(null);
    setRefined(false);
    setRefining(false);
    setModelUsed("");
    setRunning(true);

    const ctrl = new AbortController();
    abortRef.current = ctrl;
    const params = new URLSearchParams({
      task,
      max_steps: "3",
      model,
      review: String(review),
    });
    if (scope.length) params.set("repository_ids", scope.join(","));
    const url = `${BASE_URL}/api/v1/agents/run/stream?${params.toString()}`;

    try {
      for await (const ev of readSse(url, { signal: ctrl.signal })) {
        const data = JSON.parse(ev.data);
        if (ev.event === "plan") setPlan(data.plan ?? []);
        else if (ev.event === "step")
          setSteps((p) => [
            ...p,
            {
              title: data.title,
              finding: data.finding ?? "",
              citations: data.citations ?? [],
              error: data.error ?? null,
            },
          ]);
        else if (ev.event === "synthesis") {
          setSynthesis(data.synthesis ?? "");
          if (data.refined) {
            setRefined(true);
            setRefining(false);
          }
        } else if (ev.event === "refining") setRefining(true);
        else if (ev.event === "review")
          setCritic({ verdict: data.verdict, notes: data.notes });
        else if (ev.event === "done") setModelUsed(data.model ?? "");
        else if (ev.event === "error") setError(data.message ?? "Agent run failed");
      }
    } catch (err) {
      if (!ctrl.signal.aborted) {
        setError(err instanceof Error ? err.message : "stream failed");
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  const hasResult =
    plan.length > 0 || steps.length > 0 || synthesis.length > 0 || critic !== null;

  // Rough token estimate (~4 chars/token) — surfaces cost awareness on the free tier.
  const estTokens = useMemo(() => {
    const text = [
      task,
      ...plan,
      ...steps.map((s) => s.finding),
      synthesis,
      critic?.notes ?? "",
    ].join(" ");
    return Math.round(text.length / 4);
  }, [task, plan, steps, synthesis, critic]);

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
          A multi-agent pipeline, streamed live: a <strong>planner</strong> splits
          your task into sub-questions, <strong>researcher</strong> agents answer
          each from your code, a <strong>synthesizer</strong> combines them, and a{" "}
          <strong>critic</strong> fact-checks the result. Token-intensive — uses the
          model below.
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
          <label className="flex cursor-pointer items-center gap-1.5 text-muted-foreground">
            <input
              type="checkbox"
              checked={review}
              onChange={(e) => setReview(e.target.checked)}
              className="accent-violet-500"
            />
            <span>fact-check the answer (critic)</span>
          </label>
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
        <div className="flex items-center gap-2">
          <Button
            type="submit"
            loading={running}
            className="bg-gradient-to-r from-violet-500 to-fuchsia-500"
          >
            <Play className="mr-1 h-4 w-4" /> Run agents
          </Button>
          {running ? (
            <Button type="button" variant="outline" onClick={stop}>
              <Square className="mr-1 h-4 w-4" /> Stop
            </Button>
          ) : null}
        </div>
        {error ? <div className="text-sm text-destructive">{error}</div> : null}
      </form>

      {hasResult ? (
        <div className="space-y-4">
          {plan.length ? (
            <Stage
              icon={<Compass className="h-4 w-4" />}
              title="Planner"
              subtitle={`${plan.length} sub-question(s)`}
              grad="from-sky-400 to-indigo-500"
            >
              <ol className="ml-4 list-decimal space-y-1 text-sm">
                {plan.map((p, i) => (
                  <li key={i}>{p}</li>
                ))}
              </ol>
            </Stage>
          ) : null}

          {steps.map((s, i) => (
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

          {running && plan.length > 0 && steps.length < plan.length ? (
            <div className="px-1 text-xs text-muted-foreground">researching…</div>
          ) : null}

          {synthesis ? (
            <Stage
              icon={<Sparkles className="h-4 w-4" />}
              title="Synthesizer"
              subtitle="Final answer"
              grad="from-violet-500 to-fuchsia-500"
            >
              {refined ? (
                <div className="mb-2 inline-flex items-center gap-1 rounded-full bg-violet-500/15 px-2 py-0.5 text-xs font-medium text-violet-400">
                  <Sparkles className="h-3 w-3" /> self-corrected after critic feedback
                </div>
              ) : null}
              <Markdown content={synthesis} />
            </Stage>
          ) : null}

          {refining ? (
            <div className="px-1 text-xs text-muted-foreground">
              critic found issues — revising the answer…
            </div>
          ) : null}

          {critic ? (
            <Stage
              icon={<ShieldCheck className="h-4 w-4" />}
              title="Critic"
              subtitle="fact-checked against the code findings"
              grad="from-amber-400 to-orange-500"
            >
              <div className="mb-2">
                <VerdictBadge verdict={critic.verdict} />
              </div>
              <Markdown content={critic.notes} />
            </Stage>
          ) : null}

          {modelUsed ? (
            <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
              <span>model: {modelUsed}</span>
              <span
                className="rounded-full border border-border px-2 py-0.5"
                title="rough estimate from response length (~4 chars/token)"
              >
                ≈ {estTokens.toLocaleString()} tokens
              </span>
            </div>
          ) : null}
        </div>
      ) : null}
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

function VerdictBadge({ verdict }: { verdict: string }) {
  const map: Record<string, string> = {
    accurate: "bg-emerald-500/15 text-emerald-400",
    issues: "bg-destructive/15 text-destructive",
    uncertain: "bg-amber-500/15 text-amber-500",
  };
  return (
    <span
      className={cn(
        "rounded-full px-2 py-0.5 text-xs font-medium capitalize",
        map[verdict] ?? "bg-muted text-muted-foreground",
      )}
    >
      {verdict}
    </span>
  );
}

function Markdown({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words prose-p:my-1.5">
      <ReactMarkdown remarkPlugins={[remarkGfm]}>{content}</ReactMarkdown>
    </div>
  );
}
