import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Search as SearchIcon } from "lucide-react";
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
    <div className="space-y-6 max-w-5xl">
      <header>
        <h1 className="text-2xl font-semibold">Search</h1>
        <p className="text-sm text-muted-foreground">
          Hybrid search over your ingested repositories. Dense (Qdrant) + lexical (Postgres
          BM25), fused with reciprocal rank fusion, optionally reranked by a cross-encoder.
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <Input
            placeholder="What do you want to find? e.g. 'render a button', 'parse yaml config'"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            autoFocus
          />
          <Button type="submit" loading={mutation.isPending}>
            <SearchIcon className="h-4 w-4 mr-1" />
            Search
          </Button>
        </div>

        <div className="flex flex-wrap items-center gap-3 text-xs">
          <div className="flex items-center gap-2">
            <span className="text-muted-foreground">Mode:</span>
            {(["hybrid", "dense", "lexical"] as SearchMode[]).map((m) => (
              <button
                key={m}
                type="button"
                onClick={() => setMode(m)}
                className={
                  "rounded px-2 py-0.5 border " +
                  (mode === m
                    ? "bg-accent text-accent-foreground border-accent"
                    : "border-border text-muted-foreground hover:text-foreground")
                }
              >
                {m}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 cursor-pointer text-muted-foreground">
            <input
              type="checkbox"
              checked={rerank}
              onChange={(e) => setRerank(e.target.checked)}
            />
            <span>rerank (cross-encoder)</span>
          </label>
        </div>

        {readyRepos.length > 0 ? (
          <div className="space-y-1 text-xs">
            <div className="text-muted-foreground">
              Scope (empty = all your ready repos):
            </div>
            <div className="flex flex-wrap gap-1">
              {readyRepos.map((r) => {
                const on = selectedRepoIds.includes(r.id);
                return (
                  <button
                    key={r.id}
                    type="button"
                    onClick={() => toggleRepo(r.id)}
                    className={
                      "rounded-full px-2 py-0.5 border text-xs " +
                      (on
                        ? "bg-primary/15 text-primary border-primary/30"
                        : "border-border text-muted-foreground hover:text-foreground")
                    }
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
            <Link className="underline" to="/repositories">
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
        {response.hits.length} hit{response.hits.length === 1 ? "" : "s"} · mode:{" "}
        {response.mode}
        {response.reranked ? " · reranked" : ""} · {response.took_ms} ms
      </div>
      {response.hits.length === 0 ? (
        <div className="text-sm text-muted-foreground">No matches.</div>
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
    <div className="rounded-lg border border-border bg-card overflow-hidden">
      <div className="flex flex-wrap justify-between items-center px-3 py-1.5 bg-muted/30 text-xs gap-2">
        <div className="flex items-center gap-2 min-w-0">
          <span className="tabular-nums text-muted-foreground">#{rank}</span>
          <Link
            to={`/repositories/${hit.repository_id}`}
            className="font-mono text-xs hover:underline truncate"
            title={hit.file_path}
          >
            {hit.file_path}
          </Link>
          <span className="text-muted-foreground">
            lines {hit.start_line}–{hit.end_line}
          </span>
        </div>
        <div className="flex items-center gap-3 text-muted-foreground tabular-nums">
          <span title="final score (RRF / rerank)">score: {hit.score.toFixed(4)}</span>
          {hit.dense_score !== null ? (
            <span title="dense (vector) score" className="hidden sm:inline">
              d: {hit.dense_score.toFixed(3)}
            </span>
          ) : null}
          {hit.lexical_score !== null ? (
            <span title="lexical (BM25) score" className="hidden sm:inline">
              l: {hit.lexical_score.toFixed(3)}
            </span>
          ) : null}
          <span className="hidden sm:inline">{hit.token_count} tok</span>
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
