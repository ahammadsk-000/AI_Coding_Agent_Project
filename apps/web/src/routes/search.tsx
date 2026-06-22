import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search as SearchIcon, FileCode } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  api,
  ApiError,
  type SearchHit,
  type SearchMode,
  type SearchResponse,
} from "@/lib/api";
import { cn } from "@/lib/utils";

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
  json: "json",
  yaml: "yaml",
  toml: "toml",
  sql: "sql",
  bash: "bash",
  dockerfile: "docker",
  make: "makefile",
  cmake: "cmake",
  ini: "ini",
};

function prismLanguage(lang: string | null): string {
  if (!lang) return "plaintext";
  return PRISM_LANG_MAP[lang] ?? "plaintext";
}

export function SearchPage() {
  // List the user's repos so they can scope the search.
  const { data: repos } = useQuery({
    queryKey: ["repos"],
    queryFn: api.listRepos,
  });
  const readyRepos = (repos ?? []).filter((r) => r.status === "ready");

  const [query, setQuery] = useState("");
  const [mode, setMode] = useState<SearchMode>("hybrid");
  const [rerank, setRerank] = useState(true);
  const [selectedRepoIds, setSelectedRepoIds] = useState<string[]>([]);
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.search({
        query,
        repository_ids: selectedRepoIds,
        k: 10,
        mode,
        rerank,
      }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Search failed"),
  });

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!query.trim()) return;
    mutation.mutate();
  }

  function toggleRepo(id: string) {
    setSelectedRepoIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  }

  return (
    <div className="max-w-5xl space-y-6">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold tracking-tight">Search</h1>
        <p className="text-sm text-muted-foreground">
          Hybrid search over your ingested repositories — dense (Qdrant) + lexical
          (Postgres BM25), fused with reciprocal rank fusion, optionally reranked.
        </p>
      </header>

      <form
        onSubmit={handleSubmit}
        className="space-y-4 rounded-xl border border-border bg-card/50 p-4 backdrop-blur"
      >
        <div className="flex gap-2">
          <div className="relative flex-1">
            <SearchIcon className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="What do you want to find? e.g. 'render a button', 'parse yaml config'"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              className="pl-10"
              autoFocus
            />
          </div>
          <Button
            type="submit"
            loading={mutation.isPending}
            className="bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            <SearchIcon className="mr-1 h-4 w-4" />
            Search
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-4 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Mode</span>
            <div className="inline-flex rounded-lg border border-border p-0.5">
              {(["hybrid", "dense", "lexical"] as SearchMode[]).map((m) => (
                <button
                  key={m}
                  type="button"
                  onClick={() => setMode(m)}
                  className={cn(
                    "rounded-md px-2.5 py-1 capitalize transition-colors",
                    mode === m
                      ? "bg-primary/15 text-primary"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {m}
                </button>
              ))}
            </div>
          </div>
          <label className="flex cursor-pointer items-center gap-1.5 text-muted-foreground">
            <input
              type="checkbox"
              checked={rerank}
              onChange={(e) => setRerank(e.target.checked)}
              className="accent-sky-500"
            />
            <span>rerank (cross-encoder)</span>
          </label>
        </div>

        {readyRepos.length > 0 ? (
          <div className="space-y-1.5 text-xs">
            <div className="text-muted-foreground">
              Scope <span className="opacity-70">(empty = all ready repos)</span>
            </div>
            <div className="flex flex-wrap gap-1.5">
              {readyRepos.map((r) => {
                const on = selectedRepoIds.includes(r.id);
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => toggleRepo(r.id)}
                    className={cn(
                      "rounded-full border px-2.5 py-0.5 text-xs transition-colors",
                      on
                        ? "border-primary/30 bg-primary/15 text-primary"
                        : "border-border text-muted-foreground hover:text-foreground",
                    )}
                  >
                    {r.name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            No ready repos yet — ingest one from{" "}
            <Link className="text-primary underline" to="/repositories">
              Repositories
            </Link>{" "}
            first.
          </div>
        )}

        {error ? <div className="text-sm text-destructive">{error}</div> : null}
      </form>

      {mutation.data ? <Results response={mutation.data} /> : null}
    </div>
  );
}

function Results({ response }: { response: SearchResponse }) {
  return (
    <section className="space-y-3">
      <div className="text-xs text-muted-foreground">
        <span className="font-medium text-foreground">{response.hits.length}</span>{" "}
        hit{response.hits.length === 1 ? "" : "s"} · mode{" "}
        <span className="text-foreground">{response.mode}</span>
        {response.reranked ? " · reranked" : ""} · {response.took_ms} ms
      </div>
      {response.hits.length === 0 ? (
        <div className="rounded-xl border border-border bg-card/40 p-8 text-center text-sm text-muted-foreground">
          No matches — try a different query or switch the mode.
        </div>
      ) : (
        <div className="space-y-3">
          {response.hits.map((h, idx) => (
            <Hit key={h.chunk_id} hit={h} rank={idx + 1} />
          ))}
        </div>
      )}
    </section>
  );
}

function Hit({ hit, rank }: { hit: SearchHit; rank: number }) {
  return (
    <div className="overflow-hidden rounded-xl border border-border bg-card/60 backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border bg-muted/20 px-3 py-2 text-xs">
        <div className="flex min-w-0 items-center gap-2">
          <span className="grid h-5 w-5 shrink-0 place-items-center rounded bg-primary/10 text-[10px] font-semibold tabular-nums text-primary">
            {rank}
          </span>
          <FileCode className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
          <Link
            to={`/repositories/${hit.repository_id}`}
            className="truncate font-mono hover:underline"
            title={hit.file_path}
          >
            {hit.file_path}
          </Link>
          <span className="shrink-0 text-muted-foreground">
            :{hit.start_line}-{hit.end_line}
          </span>
          {hit.language ? (
            <span className="shrink-0 rounded border border-border px-1.5 py-0.5 text-[10px] text-muted-foreground">
              {hit.language}
            </span>
          ) : null}
        </div>
        <div className="flex items-center gap-2 tabular-nums">
          <span
            className="rounded-full bg-emerald-500/10 px-1.5 py-0.5 text-emerald-400"
            title="final score (RRF / rerank)"
          >
            {hit.score.toFixed(3)}
          </span>
          {hit.dense_score !== null ? (
            <span className="hidden text-muted-foreground sm:inline" title="dense (vector) score">
              d {hit.dense_score.toFixed(2)}
            </span>
          ) : null}
          {hit.lexical_score !== null ? (
            <span className="hidden text-muted-foreground sm:inline" title="lexical (BM25) score">
              l {hit.lexical_score.toFixed(2)}
            </span>
          ) : null}
          <span className="hidden text-muted-foreground sm:inline">{hit.token_count} tok</span>
        </div>
      </div>
      <SyntaxHighlighter
        language={prismLanguage(hit.language)}
        style={vscDarkPlus}
        showLineNumbers
        startingLineNumber={hit.start_line}
        wrapLongLines
        customStyle={{
          margin: 0,
          fontSize: "0.75rem",
          background: "rgb(30, 30, 30)",
        }}
        codeTagProps={{ style: { fontFamily: "ui-monospace, monospace" } }}
      >
        {hit.content}
      </SyntaxHighlighter>
    </div>
  );
}
