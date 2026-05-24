import { useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { Github, GitPullRequest, Bot, CheckCircle2, XCircle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api, ApiError } from "@/lib/api";

export function GitHubPage() {
  const { data: status } = useQuery({
    queryKey: ["github-status"],
    queryFn: api.githubStatus,
  });

  return (
    <div className="space-y-6 max-w-3xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Github className="h-6 w-6" /> GitHub
        </h1>
        <p className="text-sm text-muted-foreground">
          Generate pull requests and run AI code reviews on existing PRs.
        </p>
      </header>

      <section className="rounded-lg border border-border bg-card p-3 text-sm flex items-center gap-2">
        {status?.configured ? (
          status.login ? (
            <>
              <CheckCircle2 className="h-4 w-4 text-emerald-500" />
              Connected as <span className="font-mono">{status.login}</span>
              {status.name ? ` (${status.name})` : ""}
            </>
          ) : (
            <>
              <XCircle className="h-4 w-4 text-amber-500" />
              Token configured but invalid or lacking scope.
            </>
          )
        ) : (
          <>
            <XCircle className="h-4 w-4 text-destructive" />
            <span>
              No token configured. Set <code>GITHUB_TOKEN=ghp_...</code> in{" "}
              <code>.env</code> and recreate the api container.
            </span>
          </>
        )}
      </section>

      <ReviewPRSection disabled={!status?.login} />
      <CreatePRSection disabled={!status?.login} />
    </div>
  );
}

function ReviewPRSection({ disabled }: { disabled: boolean }) {
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [number, setNumber] = useState("");
  const [post, setPost] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Accept "#1", "1", "PR 1", etc. — keep only the digits.
  const prNumber = Number((number.match(/\d+/) ?? ["0"])[0]);

  const mutation = useMutation({
    mutationFn: () =>
      api.githubReviewPR({ owner, repo, number: prNumber, post_comment: post }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Review failed"),
    onSuccess: () => setError(null),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!owner || !repo || prNumber < 1) return;
    mutation.mutate();
  }

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h2 className="text-sm font-medium flex items-center gap-2">
        <Bot className="h-4 w-4 text-primary" /> AI review a pull request
      </h2>
      <form onSubmit={submit} className="grid grid-cols-[1fr_1fr_90px_auto] gap-2">
        <Input placeholder="owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
        <Input placeholder="repo" value={repo} onChange={(e) => setRepo(e.target.value)} />
        <Input placeholder="PR #" value={number} onChange={(e) => setNumber(e.target.value)} />
        <Button type="submit" loading={mutation.isPending} disabled={disabled}>
          Review
        </Button>
      </form>
      <label className="flex items-center gap-2 text-xs text-muted-foreground cursor-pointer">
        <input type="checkbox" checked={post} onChange={(e) => setPost(e.target.checked)} />
        Post the review as a PR comment
      </label>
      {error ? <div className="text-sm text-destructive">{error}</div> : null}
      {mutation.data ? (
        <div className="space-y-2">
          {mutation.data.comment_url ? (
            <a
              href={mutation.data.comment_url}
              target="_blank"
              rel="noreferrer"
              className="text-xs text-primary hover:underline"
            >
              → posted comment on the PR
            </a>
          ) : null}
          <pre className="text-xs bg-muted/30 rounded p-3 whitespace-pre-wrap max-h-96 overflow-auto">
            {mutation.data.review}
          </pre>
        </div>
      ) : null}
    </section>
  );
}

function CreatePRSection({ disabled }: { disabled: boolean }) {
  const [owner, setOwner] = useState("");
  const [repo, setRepo] = useState("");
  const [base, setBase] = useState("main");
  const [branch, setBranch] = useState("");
  const [title, setTitle] = useState("");
  const [path, setPath] = useState("");
  const [content, setContent] = useState("");
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: () =>
      api.githubCreatePR({
        owner,
        repo,
        base,
        branch,
        title,
        body: "Opened by AI Coding Agent.",
        changes: [{ path, content }],
      }),
    onError: (e: unknown) =>
      setError(e instanceof ApiError ? e.message : "Create PR failed"),
    onSuccess: () => setError(null),
  });

  function submit(e: FormEvent) {
    e.preventDefault();
    if (!owner || !repo || !branch || !title || !path) return;
    mutation.mutate();
  }

  return (
    <section className="rounded-lg border border-border bg-card p-4 space-y-3">
      <h2 className="text-sm font-medium flex items-center gap-2">
        <GitPullRequest className="h-4 w-4 text-primary" /> Create a pull request
      </h2>
      <form onSubmit={submit} className="space-y-2">
        <div className="grid grid-cols-2 gap-2">
          <Input placeholder="owner" value={owner} onChange={(e) => setOwner(e.target.value)} />
          <Input placeholder="repo" value={repo} onChange={(e) => setRepo(e.target.value)} />
          <Input placeholder="base branch (main)" value={base} onChange={(e) => setBase(e.target.value)} />
          <Input placeholder="new branch" value={branch} onChange={(e) => setBranch(e.target.value)} />
        </div>
        <Input placeholder="PR title" value={title} onChange={(e) => setTitle(e.target.value)} />
        <Input placeholder="file path (e.g. notes.md)" value={path} onChange={(e) => setPath(e.target.value)} />
        <textarea
          placeholder="file content"
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={4}
          className="w-full font-mono text-sm rounded-md bg-card border border-border px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
        />
        <Button type="submit" loading={mutation.isPending} disabled={disabled}>
          <GitPullRequest className="h-4 w-4 mr-1" /> Create PR
        </Button>
      </form>
      {error ? <div className="text-sm text-destructive">{error}</div> : null}
      {mutation.data ? (
        <a
          href={mutation.data.url}
          target="_blank"
          rel="noreferrer"
          className="text-sm text-primary hover:underline"
        >
          → opened PR #{mutation.data.number} ({mutation.data.branch})
        </a>
      ) : null}
    </section>
  );
}
