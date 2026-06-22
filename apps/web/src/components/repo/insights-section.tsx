import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Network, GitFork, BookOpen } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import { Mermaid } from "@/components/mermaid";
import { api, ApiError } from "@/lib/api";

export function InsightsSection({ repoId }: { repoId: string }) {
  const [error, setError] = useState<string | null>(null);
  const onErr = (e: unknown) =>
    setError(e instanceof ApiError ? e.message : "request failed");

  const diagram = useMutation({
    mutationFn: () => api.repoDiagram(repoId),
    onError: onErr,
    onSuccess: () => setError(null),
  });
  const codemap = useMutation({
    mutationFn: () => api.repoCodemap(repoId),
    onError: onErr,
    onSuccess: () => setError(null),
  });
  const docs = useMutation({
    mutationFn: () => api.repoDocs(repoId),
    onError: onErr,
    onSuccess: () => setError(null),
  });

  return (
    <section className="space-y-3">
      <h2 className="text-sm font-medium">Insights</h2>
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          loading={diagram.isPending}
          onClick={() => {
            setError(null);
            diagram.mutate();
          }}
        >
          <Network className="mr-1 h-4 w-4" /> Architecture diagram
        </Button>
        <Button
          variant="outline"
          size="sm"
          loading={codemap.isPending}
          onClick={() => {
            setError(null);
            codemap.mutate();
          }}
        >
          <GitFork className="mr-1 h-4 w-4" /> Code map
        </Button>
        <Button
          variant="outline"
          size="sm"
          loading={docs.isPending}
          onClick={() => {
            setError(null);
            docs.mutate();
          }}
        >
          <BookOpen className="mr-1 h-4 w-4" /> Onboarding docs
        </Button>
      </div>
      <p className="text-xs text-muted-foreground">
        Architecture diagram &amp; onboarding docs are LLM-generated (uses tokens).
        The code map is built directly from the symbols extracted during ingestion.
      </p>
      {error ? <div className="text-sm text-destructive">{error}</div> : null}

      {diagram.data ? (
        <InsightCard title="Architecture diagram">
          <Mermaid code={diagram.data.mermaid} />
        </InsightCard>
      ) : null}
      {codemap.data ? (
        <InsightCard title="Code map">
          <Mermaid code={codemap.data.mermaid} />
        </InsightCard>
      ) : null}
      {docs.data ? (
        <InsightCard title="Onboarding docs">
          <div className="prose prose-invert prose-sm max-w-none break-words">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{docs.data.markdown}</ReactMarkdown>
          </div>
        </InsightCard>
      ) : null}
    </section>
  );
}

function InsightCard({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div className="rounded-xl border border-border bg-card/60 p-4 backdrop-blur">
      <div className="mb-2 text-sm font-medium">{title}</div>
      {children}
    </div>
  );
}
