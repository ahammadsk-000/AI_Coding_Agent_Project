import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Trash2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type Memory, type MemoryScope } from "@/lib/api";
import { cn } from "@/lib/utils";

const SCOPE_COLORS: Record<MemoryScope, string> = {
  user: "bg-primary/15 text-primary",
  project: "bg-emerald-500/15 text-emerald-500",
  conversation: "bg-amber-500/15 text-amber-500",
};

export function MemoryPage() {
  const qc = useQueryClient();
  const { data: memories, isLoading } = useQuery({
    queryKey: ["memories"],
    queryFn: () => api.listMemories(),
    refetchInterval: 10_000,
  });

  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);

  const createMutation = useMutation({
    mutationFn: () => api.createMemory({ content, scope: "user" }),
    onSuccess: () => {
      setContent("");
      setError(null);
      qc.invalidateQueries({ queryKey: ["memories"] });
    },
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Failed to save memory"),
  });

  const deleteMutation = useMutation({
    mutationFn: (id: string) => api.deleteMemory(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["memories"] }),
  });

  function handleAdd(e: FormEvent) {
    e.preventDefault();
    if (!content.trim()) return;
    createMutation.mutate();
  }

  return (
    <div className="max-w-3xl space-y-6">
      <header className="space-y-1">
        <div className="flex items-center gap-2.5">
          <div className="grid h-9 w-9 place-items-center rounded-xl bg-gradient-to-br from-amber-400 to-orange-500 shadow-md">
            <Brain className="h-5 w-5 text-white" />
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">Memory</h1>
        </div>
        <p className="text-sm text-muted-foreground">
          Durable facts the assistant recalls across conversations. Add notes
          here, or just tell the assistant "remember that ..." in a chat.
        </p>
      </header>

      <section className="rounded-xl border border-border bg-card/50 p-4 backdrop-blur">
        <form onSubmit={handleAdd} className="flex gap-2">
          <Input
            placeholder="e.g. I prefer TypeScript over JavaScript for new code"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <Button
            type="submit"
            loading={createMutation.isPending}
            className="bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            <Plus className="mr-1 h-4 w-4" /> Remember
          </Button>
        </form>
        {error ? <div className="mt-2 text-sm text-destructive">{error}</div> : null}
      </section>

      <section className="space-y-2">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (memories ?? []).length === 0 ? (
          <div className="rounded-xl border border-border bg-card/40 p-8 text-center text-sm text-muted-foreground">
            No memories yet. Add one above, or say "remember that ..." in a chat.
          </div>
        ) : (
          (memories ?? []).map((m) => (
            <MemoryItem
              key={m.id}
              memory={m}
              onDelete={() => deleteMutation.mutate(m.id)}
            />
          ))
        )}
      </section>
    </div>
  );
}

function MemoryItem({ memory, onDelete }: { memory: Memory; onDelete: () => void }) {
  return (
    <div className="group flex items-start justify-between gap-3 rounded-xl border border-border bg-card/60 p-3.5 backdrop-blur transition-colors hover:border-primary/30">
      <div className="min-w-0 space-y-1.5">
        <div className="text-sm">{memory.content}</div>
        <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
          <span className={cn("rounded-full px-2 py-0.5 capitalize", SCOPE_COLORS[memory.scope])}>
            {memory.scope}
          </span>
          <span className="capitalize">{memory.source}</span>
          {memory.access_count > 0 ? <span>· recalled {memory.access_count}×</span> : null}
        </div>
      </div>
      <button
        onClick={() => {
          if (confirm("Forget this memory?")) onDelete();
        }}
        className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
        title="Forget"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
