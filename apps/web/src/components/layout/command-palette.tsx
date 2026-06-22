import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import {
  LayoutDashboard,
  GitBranch,
  Search,
  MessageSquare,
  Workflow,
  Brain,
  Terminal,
  Github,
  Settings,
} from "lucide-react";

import { SANDBOX_ENABLED } from "@/lib/features";
import { cn } from "@/lib/utils";

interface Command {
  label: string;
  to: string;
  icon: ReactNode;
}

const COMMANDS: Command[] = [
  { label: "Dashboard", to: "/dashboard", icon: <LayoutDashboard className="h-4 w-4" /> },
  { label: "Repositories", to: "/repositories", icon: <GitBranch className="h-4 w-4" /> },
  { label: "Search", to: "/search", icon: <Search className="h-4 w-4" /> },
  { label: "Chat", to: "/chat", icon: <MessageSquare className="h-4 w-4" /> },
  { label: "Agents", to: "/agents", icon: <Workflow className="h-4 w-4" /> },
  { label: "Memory", to: "/memory", icon: <Brain className="h-4 w-4" /> },
  ...(SANDBOX_ENABLED
    ? [{ label: "Sandbox", to: "/sandbox", icon: <Terminal className="h-4 w-4" /> }]
    : []),
  { label: "GitHub", to: "/github", icon: <Github className="h-4 w-4" /> },
  { label: "Settings", to: "/settings", icon: <Settings className="h-4 w-4" /> },
];

export function CommandPalette() {
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "Escape") {
        setOpen(false);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 0);
    }
  }, [open]);

  const results = useMemo(() => {
    const s = q.trim().toLowerCase();
    return s ? COMMANDS.filter((c) => c.label.toLowerCase().includes(s)) : COMMANDS;
  }, [q]);

  if (!open) return null;

  function go(to: string) {
    setOpen(false);
    navigate(to);
  }

  function onInputKey(e: React.KeyboardEvent) {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive((a) => Math.min(a + 1, results.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive((a) => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const r = results[active];
      if (r) go(r.to);
    }
  }

  return (
    <>
      <div className="fixed inset-0 z-50 bg-black/50" onClick={() => setOpen(false)} />
      <div className="fixed left-1/2 top-24 z-50 w-full max-w-lg -translate-x-1/2 overflow-hidden rounded-xl border border-border bg-background shadow-2xl">
        <input
          ref={inputRef}
          value={q}
          onChange={(e) => {
            setQ(e.target.value);
            setActive(0);
          }}
          onKeyDown={onInputKey}
          placeholder="Jump to… (type to filter)"
          className="w-full border-b border-border bg-transparent px-4 py-3 text-sm focus:outline-none"
        />
        <div className="max-h-80 overflow-auto p-1">
          {results.length === 0 ? (
            <div className="px-3 py-4 text-sm text-muted-foreground">No matches.</div>
          ) : (
            results.map((c, i) => (
              <button
                key={c.to}
                onClick={() => go(c.to)}
                onMouseEnter={() => setActive(i)}
                className={cn(
                  "flex w-full items-center gap-2.5 rounded-md px-3 py-2 text-sm transition-colors",
                  i === active
                    ? "bg-primary/10 text-foreground"
                    : "text-muted-foreground hover:bg-accent/50",
                )}
              >
                <span className={i === active ? "text-primary" : ""}>{c.icon}</span>
                {c.label}
              </button>
            ))
          )}
        </div>
        <div className="border-t border-border px-3 py-1.5 text-[10px] text-muted-foreground">
          ↑↓ navigate · ↵ open · esc close · ⌘/Ctrl+K toggle
        </div>
      </div>
    </>
  );
}
