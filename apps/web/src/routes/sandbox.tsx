import { useRef, useState, type FormEvent } from "react";
import { useQuery } from "@tanstack/react-query";
import { Terminal, Play, ShieldAlert } from "lucide-react";

import { Button } from "@/components/ui/button";
import { api, type SandboxEvent } from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";

type RunState = "idle" | "running" | "needs-approval";

export function SandboxPage() {
  const { data: repos } = useQuery({ queryKey: ["repos"], queryFn: api.listRepos });
  const readyRepos = (repos ?? []).filter((r) => r.status === "ready");

  const [command, setCommand] = useState("");
  const [repoId, setRepoId] = useState<string>("");
  const [output, setOutput] = useState("");
  const [state, setState] = useState<RunState>("idle");
  const [verdict, setVerdict] = useState<{ verdict: string; reason: string } | null>(null);
  const [exitInfo, setExitInfo] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);

  function run(approved: boolean) {
    const token = useAuthStore.getState().accessToken;
    if (!token || !command.trim()) return;
    setOutput("");
    setExitInfo(null);
    setVerdict(null);
    setState("running");

    const ws = new WebSocket(api.sandboxWsUrl(token));
    wsRef.current = ws;
    ws.onopen = () =>
      ws.send(
        JSON.stringify({
          command,
          repository_id: repoId || null,
          approved,
        }),
      );
    ws.onmessage = (ev) => {
      const e = JSON.parse(ev.data) as SandboxEvent;
      if (e.kind === "classify") {
        setVerdict({ verdict: e.verdict, reason: e.reason });
      } else if (e.kind === "needs_approval") {
        setState("needs-approval");
        setExitInfo(e.text);
      } else if (e.kind === "output") {
        setOutput((o) => o + e.text);
      } else if (e.kind === "status") {
        setOutput((o) => o + `\n\x1b[2m• ${e.text}\x1b[0m\n`);
      } else if (e.kind === "exit") {
        setExitInfo(`exited with code ${e.exit_code}`);
      } else if (e.kind === "error") {
        setExitInfo(`error: ${e.text}`);
      }
    };
    ws.onclose = () => {
      if (state !== "needs-approval") setState("idle");
      wsRef.current = null;
    };
    ws.onerror = () => {
      setExitInfo("WebSocket error");
      setState("idle");
    };
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    run(false);
  }

  return (
    <div className="space-y-6 max-w-5xl">
      <header className="space-y-1">
        <h1 className="text-2xl font-semibold flex items-center gap-2">
          <Terminal className="h-6 w-6 text-primary" /> Sandbox
        </h1>
        <p className="text-sm text-muted-foreground">
          Run shell commands in a throwaway, network-isolated container with CPU/memory
          limits and a hard timeout. Select a repo to run against its code (read-only copy).
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <select
            value={repoId}
            onChange={(e) => setRepoId(e.target.value)}
            className="rounded-md bg-card border border-border px-2 py-2 text-sm"
          >
            <option value="">(no repo)</option>
            {readyRepos.map((r) => (
              <option key={r.id} value={r.id}>
                {r.name}
              </option>
            ))}
          </select>
          <input
            value={command}
            onChange={(e) => setCommand(e.target.value)}
            placeholder="e.g. ls -la  •  python --version  •  cat README.md"
            className="flex-1 font-mono text-sm rounded-md bg-card border border-border px-3 py-2 focus:outline-none focus:ring-1 focus:ring-primary"
          />
          <Button type="submit" loading={state === "running"} disabled={!command.trim()}>
            <Play className="h-4 w-4 mr-1" /> Run
          </Button>
        </div>

        {verdict ? (
          <div className="text-xs text-muted-foreground">
            policy: <span className="font-mono">{verdict.verdict}</span> — {verdict.reason}
          </div>
        ) : null}

        {state === "needs-approval" ? (
          <div className="rounded-md border border-amber-500/40 bg-amber-500/10 p-3 text-sm space-y-2">
            <div className="flex items-center gap-2 text-amber-500">
              <ShieldAlert className="h-4 w-4" /> Approval required
            </div>
            <div className="text-xs text-muted-foreground">{exitInfo}</div>
            <Button size="sm" variant="outline" onClick={() => run(true)}>
              Run anyway
            </Button>
          </div>
        ) : null}
      </form>

      <section>
        <div className="text-xs text-muted-foreground mb-1">Output</div>
        <pre className="rounded-lg border border-border bg-[rgb(20,20,20)] text-xs text-green-300 font-mono p-3 min-h-[12rem] max-h-[28rem] overflow-auto whitespace-pre-wrap">
{output.replace(/\x1b\[\d+m/g, "") || "(no output yet)"}
        </pre>
        {exitInfo && state !== "needs-approval" ? (
          <div className="text-xs text-muted-foreground mt-1">{exitInfo}</div>
        ) : null}
      </section>

      <div className="text-xs text-muted-foreground border-t border-border pt-3">
        Isolation: no network · dropped capabilities · read-only root · non-root user ·
        {" "}memory + CPU + PID caps · auto-killed after the configured timeout.
      </div>
    </div>
  );
}
