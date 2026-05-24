import { useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Brain, Trash2, Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type Memory, type MemoryScope } from "@/lib/api";

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
    <div className="space-y-6 max-w-3xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Brain className="h-6 w-6 text-primary" /> Memory
        </h1>
        <p className="text-sm text-muted-foreground">
          Durable facts the assistant recalls across conversations. Add notes here,
          or just tell the assistant "remember that ..." in a chat.
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-4">
        <form onSubmit={handleAdd} className="flex gap-2">
          <Input
            placeholder="e.g. I prefer TypeScript over JavaScript for new code"
            value={content}
            onChange={(e) => setContent(e.target.value)}
          />
          <Button type="submit" loading={createMutation.isPending}>
            <Plus className="h-4 w-4 mr-1" /> Remember
          </Button>
        </form>
        {error ? <div className="text-sm text-destructive mt-2">{error}</div> : null}
      </section>

      <section className="space-y-2">
        {isLoading ? (
          <div className="text-sm text-muted-foreground">Loading…</div>
        ) : (memories ?? []).length === 0 ? (
          <div className="text-sm text-muted-foreground">
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

function MemoryItem({
  memory,
  onDelete,
}: {
  memory: Memory;
  onDelete: () => void;
}) {
  return (
    <div className="rounded-lg border border-border bg-card p-3 flex items-start justify-between gap-3">
      <div className="min-w-0 space-y-1">
        <div className="text-sm">{memory.content}</div>
        <div className="flex items-center gap-2 text-xs text-muted-foreground">
          <span className={"rounded px-1.5 py-0.5 " + SCOPE_COLORS[memory.scope]}>
            {memory.scope}
          </span>
          <span>{memory.source}</span>
          {memory.access_count > 0 ? (
            <span>· recalled {memory.access_count}×</span>
          ) : null}
        </div>
      </div>
      <button
        onClick={() => {
          if (confirm("Forget this memory?")) onDelete();
        }}
        className="text-muted-foreground hover:text-destructive"
        title="Forget"
      >
        <Trash2 className="h-4 w-4" />
      </button>
    </div>
  );
}
