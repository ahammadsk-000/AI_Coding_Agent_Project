import { useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { X, GitPullRequest } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError, type ChatCitation } from "@/lib/api";

// Pull the first fenced ```lang code block out of a markdown string.
const FENCE_RE = /```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/;

export function extractFirstCodeBlock(
  markdown: string,
): { lang: string; code: string } | null {
  const m = FENCE_RE.exec(markdown);
  if (!m) return null;
  const code = (m[2] ?? "").replace(/\n$/, "");
  if (!code.trim()) return null;
  return { lang: m[1] || "plaintext", code };
}

function parseGithub(url: string): { owner: string; repo: string } | null {
  const m = url.match(/github\.com[/:]([^/]+)\/([^/.\s]+)/i);
  if (!m || !m[1] || !m[2]) return null;
  return { owner: m[1], repo: m[2] };
}

// ---------- citation → inline code panel ----------

export function CitationPanel({
  citation,
  onClose,
}: {
  citation: ChatCitation;
  onClose: () => void;
}) {
  const { data: chunks, isLoading } = useQuery({
    queryKey: ["chunks", citation.repository_id, citation.file_id],
    queryFn: () => api.listFileChunks(citation.repository_id, citation.file_id),
  });

  const shown = useMemo(() => {
    const all = chunks ?? [];
    const overlap = all.filter(
      (c) => !(c.end_line < citation.start_line || c.start_line > citation.end_line),
    );
    return overlap.length ? overlap : all;
  }, [chunks, citation.start_line, citation.end_line]);

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/40" onClick={onClose} />
      <aside className="fixed inset-y-0 right-0 z-50 flex w-full max-w-xl flex-col border-l border-border bg-background shadow-2xl">
        <div className="flex items-center justify-between border-b border-border p-3">
          <div className="min-w-0">
            <div className="truncate font-mono text-sm">{citation.file_path}</div>
            <div className="text-xs text-muted-foreground">
              lines {citation.start_line}–{citation.end_line}
            </div>
          </div>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
            title="Close"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <div className="flex-1 space-y-3 overflow-auto p-3">
          {isLoading ? (
            <div className="text-sm text-muted-foreground">Loading…</div>
          ) : shown.length === 0 ? (
            <div className="text-sm text-muted-foreground">
              No code found for this citation.
            </div>
          ) : (
            shown.map((c) => (
              <div key={c.id} className="overflow-hidden rounded-lg border border-border">
                <div className="bg-muted/30 px-2 py-1 text-xs text-muted-foreground">
                  lines {c.start_line}–{c.end_line}
                </div>
                <SyntaxHighlighter
                  language={c.language ?? "plaintext"}
                  style={vscDarkPlus}
                  showLineNumbers
                  startingLineNumber={c.start_line}
                  wrapLongLines
                  customStyle={{ margin: 0, fontSize: "0.75rem", background: "rgb(30,30,30)" }}
                  codeTagProps={{ style: { fontFamily: "ui-monospace, monospace" } }}
                >
                  {c.content}
                </SyntaxHighlighter>
              </div>
            ))
          )}
        </div>
      </aside>
    </>
  );
}

// ---------- "open as PR" modal ----------

export function PrModal({
  initial,
  onClose,
}: {
  initial: { code: string; lang: string; path?: string };
  onClose: () => void;
}) {
  const { data: repos } = useQuery({ queryKey: ["repos"], queryFn: api.listRepos });

  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [branch, setBranch] = useState(`aca-edit-${Date.now().toString(36)}`);
  const [path, setPath] = useState(initial.path ?? "");
  const [title, setTitle] = useState("Update from AI Coding Agent");
  const [content, setContent] = useState(initial.code);
  const [error, setError] = useState<string | null>(null);

  function pickRepo(id: string) {
    const r = (repos ?? []).find((x) => x.id === id);
    if (!r) return;
    const parsed = parseGithub(r.url);
    if (parsed) {
      setOwner(parsed.owner);
      setRepo(parsed.repo);
    }
  }

  const mutation = useMutation({
    mutationFn: () =>
      api.githubCreatePR({
        owner,
        repo,
        base: "main",
        branch,
        title,
        body: "Proposed by the AI Coding Agent from a chat answer.",
        changes: [{ path, content }],
      }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Create PR failed"),
    onSuccess: () => setError(null),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    setError(null);
    if (!owner || !repo || !branch || !title || !path) {
      setError("Fill owner, repo, branch, title, and file path.");
      return;
    }
    mutation.mutate();
  }

  return (
    <>
      <div className="fixed inset-0 z-40 bg-black/50" onClick={onClose} />
      <div className="fixed left-1/2 top-1/2 z-50 max-h-[90vh] w-full max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-auto rounded-xl border border-border bg-background p-5 shadow-2xl">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="flex items-center gap-2 font-medium">
            <GitPullRequest className="h-4 w-4 text-primary" /> Open as pull request
          </h2>
          <button
            onClick={onClose}
            className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>
        <p className="mb-3 text-xs text-muted-foreground">
          Commits this content to a new branch and opens a PR. Requires a GitHub
          token with repo write access. The file at the path below is{" "}
          <strong>replaced</strong> with this content — review it first.
        </p>
        <form onSubmit={submit} className="space-y-2">
          {(repos ?? []).length ? (
            <select
              onChange={(e) => pickRepo(e.target.value)}
              defaultValue=""
              className="w-full rounded-md border border-border bg-card/60 px-2 py-1.5 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
            >
              <option value="" disabled>
                Prefill owner/repo from an ingested repo…
              </option>
              {(repos ?? []).map((r) => (
                <option key={r.id} value={r.id}>
                  {r.name}
                </option>
              ))}
            </select>
          ) : null}
          <div className="grid grid-cols-2 gap-2">
            <Input placeholder="owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
            <Input placeholder="repo" value={repo} onChange={(e) => setRepo(e.target.value)} />
            <Input placeholder="new branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
            <Input placeholder="file path (e.g. notes.md)" value={path} onChange={(e) => setPath(e.target.value)} />
          </div>
          <Input placeholder="PR title" value={title} onChange={(e) => setTitle(e.target.value)} />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            rows={8}
            className="w-full rounded-md border border-border bg-card/60 px-3 py-2 font-mono text-xs focus:outline-none focus:ring-2 focus:ring-ring"
          />
          {error ? <div className="text-sm text-destructive">{error}</div> : null}
          {mutation.data ? (
            <a
              href={mutation.data.url}
              target="_blank"
              rel="noreferrer"
              className="block text-sm text-primary hover:underline"
            >
              → opened PR #{mutation.data.number} ({mutation.data.branch})
            </a>
          ) : null}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" onClick={onClose}>
              Close
            </Button>
            <Button
              type="submit"
              loading={mutation.isPending}
              className="bg-gradient-to-r from-sky-500 to-indigo-500"
            >
              <GitPullRequest className="mr-1 h-4 w-4" /> Open PR
            </Button>
          </div>
        </form>
      </div>
    </>
  );
}
