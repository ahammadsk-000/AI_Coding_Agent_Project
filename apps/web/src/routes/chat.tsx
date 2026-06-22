import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, Link } from "react-router-dom";
import {
  Plus,
  Send,
  Trash2,
  Wrench,
  Quote,
  Square,
  Copy,
  Check,
  Pencil,
  Sparkles,
  MessageSquare,
} from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import { Button } from "@/components/ui/button";
import {
  api,
  ApiError,
  type ChatCitation,
  type ChatMessage,
  type Conversation,
  type WsEvent,
} from "@/lib/api";
import { useAuthStore } from "@/stores/auth-store";
import { cn, initials } from "@/lib/utils";

// Models for new conversations (Groq, via the OpenAI-compatible provider).
const MODELS = [
  { id: "llama-3.3-70b-versatile", label: "Llama 3.3 70B · quality" },
  { id: "llama-3.1-8b-instant", label: "Llama 3.1 8B · fast" },
];

export function ChatPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const [model, setModel] = useState(MODELS[0]!.id);

  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: api.listConversations,
    refetchInterval: 10_000,
  });

  const createConv = useMutation({
    mutationFn: () => api.createConversation({ llm_model: model }),
    onSuccess: (c) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      navigate(`/chat/${c.id}`);
    },
  });

  const deleteConv = useMutation({
    mutationFn: (cid: string) => api.deleteConversation(cid),
    onSuccess: (_, cid) => {
      qc.invalidateQueries({ queryKey: ["conversations"] });
      if (id === cid) navigate("/chat");
    },
  });

  return (
    <div className="grid h-[calc(100vh-3rem)] grid-cols-[18rem_1fr] gap-4">
      <aside className="flex flex-col overflow-hidden rounded-xl border border-border bg-card/40 backdrop-blur">
        <div className="space-y-2 border-b border-border p-3">
          <div className="flex items-center justify-between">
            <span className="text-sm font-semibold">Conversations</span>
            <Button
              size="sm"
              onClick={() => createConv.mutate()}
              className="bg-gradient-to-r from-sky-500 to-indigo-500"
            >
              <Plus className="mr-1 h-4 w-4" /> New
            </Button>
          </div>
          <select
            value={model}
            onChange={(e) => setModel(e.target.value)}
            title="Model for new conversations"
            className="w-full rounded-md border border-border bg-card/60 px-2 py-1.5 text-xs text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring"
          >
            {MODELS.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>
        <div className="flex-1 space-y-1 overflow-auto p-2">
          {(conversations ?? []).length === 0 ? (
            <div className="p-3 text-xs text-muted-foreground">
              No chats yet — click "New" to start one.
            </div>
          ) : (
            (conversations ?? []).map((c) => (
              <ConvItem
                key={c.id}
                conv={c}
                active={c.id === id}
                onDelete={() => deleteConv.mutate(c.id)}
              />
            ))
          )}
        </div>
      </aside>

      <section className="flex min-w-0 flex-col">
        {id ? (
          <ChatThread conversationId={id} />
        ) : (
          <EmptyChat onNew={() => createConv.mutate()} />
        )}
      </section>
    </div>
  );
}

function ConvItem({
  conv,
  active,
  onDelete,
}: {
  conv: Conversation;
  active: boolean;
  onDelete: () => void;
}) {
  return (
    <div
      className={cn(
        "group relative flex items-center gap-2 rounded-lg px-2 py-2 text-sm transition-colors",
        active
          ? "bg-primary/10 text-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground",
      )}
    >
      {active ? (
        <span className="absolute left-0 top-1/2 h-5 w-1 -translate-y-1/2 rounded-r-full bg-gradient-to-b from-sky-400 to-indigo-500" />
      ) : null}
      <Link to={`/chat/${conv.id}`} className="min-w-0 flex-1">
        <div className="truncate font-medium">{conv.title}</div>
        {conv.last_message_preview ? (
          <div className="truncate text-xs text-muted-foreground">
            {conv.last_message_preview}
          </div>
        ) : (
          <div className="truncate text-xs text-muted-foreground">
            {conv.llm_provider} · {conv.llm_model}
          </div>
        )}
      </Link>
      <button
        onClick={(e) => {
          e.preventDefault();
          if (confirm(`Delete "${conv.title}"?`)) onDelete();
        }}
        className="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
        title="Delete"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function EmptyChat({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex flex-1 items-center justify-center text-center">
      <div className="max-w-md space-y-4">
        <div className="mx-auto grid h-14 w-14 place-items-center rounded-2xl bg-gradient-to-br from-sky-400 to-indigo-500 shadow-lg shadow-sky-500/20">
          <MessageSquare className="h-7 w-7 text-white" />
        </div>
        <h2 className="text-xl font-semibold">Chat with your code</h2>
        <p className="text-sm text-muted-foreground">
          Ask questions about any of your ingested repositories. The agent
          retrieves relevant code, calls read-only tools, and streams its answer
          with citations.
        </p>
        <div className="flex flex-wrap justify-center gap-2">
          {[
            "What does this repository do?",
            "Summarize the main files",
            "Explain the entry point",
          ].map((q) => (
            <span
              key={q}
              className="rounded-full border border-border bg-card/60 px-3 py-1 text-xs text-muted-foreground"
            >
              {q}
            </span>
          ))}
        </div>
        <Button
          onClick={onNew}
          className="bg-gradient-to-r from-sky-500 to-indigo-500"
        >
          <Plus className="mr-1 h-4 w-4" /> Start a new chat
        </Button>
      </div>
    </div>
  );
}

// ---------- thread ----------

interface StreamingState {
  buffer: string;
  toolEvents: Array<
    | { kind: "start"; call_id: string; name: string; arguments: Record<string, unknown> }
    | { kind: "result"; call_id: string; summary: string }
  >;
  citations: ChatCitation[];
}

function ChatThread({ conversationId }: { conversationId: string }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["conversation", conversationId],
    queryFn: () => api.getConversation(conversationId),
  });

  const user = useAuthStore((s) => s.user);
  const userInitials = initials(user?.full_name || user?.email || "?");

  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState<StreamingState | null>(null);
  const [error, setError] = useState<string | null>(null);

  const wsRef = useRef<WebSocket | null>(null);
  const bottomRef = useRef<HTMLDivElement | null>(null);

  // Auto-scroll on new content
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [data, streaming]);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!input.trim() || streaming) return;
    const content = input;
    setInput("");
    setError(null);
    sendOverWs(content);
  }

  function stopGeneration() {
    // Closing the socket aborts the server-side stream (its next send fails,
    // which tears down the LLM request). The partial reply is kept by the
    // backend if any text was produced.
    wsRef.current?.close();
  }

  function sendOverWs(content: string) {
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      setError("Not authenticated.");
      return;
    }
    setStreaming({ buffer: "", toolEvents: [], citations: [] });

    const ws = new WebSocket(api.conversationWsUrl(conversationId, token));
    wsRef.current = ws;

    ws.onopen = () => {
      ws.send(JSON.stringify({ content }));
    };
    ws.onmessage = (ev) => {
      try {
        const event = JSON.parse(ev.data) as WsEvent;
        setStreaming((prev) => {
          if (!prev) return prev;
          if (event.type === "token") {
            return { ...prev, buffer: prev.buffer + event.delta };
          }
          if (event.type === "tool_call_start") {
            return {
              ...prev,
              toolEvents: [
                ...prev.toolEvents,
                {
                  kind: "start",
                  call_id: event.call_id,
                  name: event.name,
                  arguments: event.arguments,
                },
              ],
            };
          }
          if (event.type === "tool_call_result") {
            return {
              ...prev,
              toolEvents: [
                ...prev.toolEvents,
                { kind: "result", call_id: event.call_id, summary: event.summary },
              ],
            };
          }
          if (event.type === "citations") {
            return {
              ...prev,
              citations: [...prev.citations, ...event.citations],
            };
          }
          if (event.type === "error") {
            setError(event.message);
          }
          return prev;
        });
      } catch {
        // ignore
      }
    };
    ws.onerror = () => {
      setError("WebSocket error — server may be unreachable.");
    };
    ws.onclose = () => {
      // Refetch the conversation so persisted messages replace the streaming buffer.
      qc.invalidateQueries({ queryKey: ["conversation", conversationId] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
      setStreaming(null);
      wsRef.current = null;
    };
  }

  if (isLoading) {
    return <div className="text-sm text-muted-foreground">Loading conversation…</div>;
  }
  if (!data) {
    return <div className="text-sm text-destructive">Conversation not found.</div>;
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <ChatHeader
        conversationId={conversationId}
        title={data.conversation.title}
        provider={data.conversation.llm_provider}
        model={data.conversation.llm_model}
      />

      <div className="flex-1 space-y-5 overflow-auto py-5">
        {data.messages
          .filter((m) => m.role !== "system" && m.role !== "tool")
          .map((m) => (
            <MessageBubble key={m.id} message={m} userInitials={userInitials} />
          ))}
        {streaming ? <StreamingBubble state={streaming} /> : null}
        {error ? <div className="text-xs text-destructive">{error}</div> : null}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="flex items-end gap-2 border-t border-border pt-3"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          placeholder="Ask about your code — try 'What does index.html do?'"
          className="flex-1 resize-none rounded-xl border border-border bg-card/60 px-3.5 py-2.5 text-sm backdrop-blur focus:outline-none focus:ring-2 focus:ring-ring"
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSubmit(e as unknown as FormEvent);
            }
          }}
          disabled={!!streaming}
        />
        {streaming ? (
          <Button type="button" variant="outline" onClick={stopGeneration}>
            <Square className="mr-1 h-4 w-4" />
            Stop
          </Button>
        ) : (
          <Button
            type="submit"
            disabled={!input.trim()}
            className="bg-gradient-to-r from-sky-500 to-indigo-500"
          >
            <Send className="mr-1 h-4 w-4" />
            Send
          </Button>
        )}
      </form>
    </div>
  );
}

function ChatHeader({
  conversationId,
  title,
  provider,
  model,
}: {
  conversationId: string;
  title: string;
  provider: string;
  model: string;
}) {
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(title);

  const renameMutation = useMutation({
    mutationFn: (t: string) => api.renameConversation(conversationId, t),
    onSuccess: () => {
      setEditing(false);
      qc.invalidateQueries({ queryKey: ["conversation", conversationId] });
      qc.invalidateQueries({ queryKey: ["conversations"] });
    },
  });

  function save() {
    const t = draft.trim();
    if (t && t !== title) renameMutation.mutate(t);
    else setEditing(false);
  }

  return (
    <header className="border-b border-border px-1 pb-3">
      {editing ? (
        <input
          autoFocus
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          onBlur={save}
          onKeyDown={(e) => {
            if (e.key === "Enter") save();
            if (e.key === "Escape") {
              setDraft(title);
              setEditing(false);
            }
          }}
          className="w-full max-w-md rounded-md border border-border bg-card px-2 py-1 text-sm font-semibold focus:outline-none focus:ring-1 focus:ring-primary"
        />
      ) : (
        <div className="group flex items-center gap-2">
          <span className="truncate text-base font-semibold">{title}</span>
          <button
            onClick={() => {
              setDraft(title);
              setEditing(true);
            }}
            className="text-muted-foreground opacity-0 transition-opacity hover:text-foreground group-hover:opacity-100"
            title="Rename"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      <div className="mt-1.5 inline-flex items-center gap-1.5 rounded-full border border-border bg-card/60 px-2 py-0.5 text-xs text-muted-foreground">
        <Sparkles className="h-3 w-3 text-primary" />
        {provider} · {model}
      </div>
    </header>
  );
}

function Avatar({ isUser, userInitials }: { isUser: boolean; userInitials: string }) {
  if (isUser) {
    return (
      <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-sky-400 to-indigo-500 text-[10px] font-semibold text-white">
        {userInitials}
      </div>
    );
  }
  return (
    <div className="mt-0.5 grid h-7 w-7 shrink-0 place-items-center rounded-full bg-gradient-to-br from-violet-500 to-fuchsia-500">
      <Sparkles className="h-3.5 w-3.5 text-white" />
    </div>
  );
}

function ToolChip({ label }: { label: string }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-md border border-border bg-muted/40 px-1.5 py-0.5 text-xs text-muted-foreground">
      <Wrench className="h-3 w-3" /> {label}
    </span>
  );
}

function MessageBubble({
  message,
  userInitials,
}: {
  message: ChatMessage;
  userInitials: string;
}) {
  const isUser = message.role === "user";
  return (
    <div className={cn("flex gap-2.5", isUser ? "flex-row-reverse" : "flex-row")}>
      <Avatar isUser={isUser} userInitials={userInitials} />
      <div
        className={cn(
          "max-w-[85%] rounded-2xl px-3.5 py-2.5 text-sm",
          isUser
            ? "bg-gradient-to-br from-sky-500/20 to-indigo-500/20 text-foreground"
            : "border border-border bg-card/60",
        )}
      >
        <MessageBody content={message.content} />
        {message.tool_calls?.length ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {message.tool_calls.map((tc, idx) => {
              const name =
                (tc as { function?: { name?: string } }).function?.name ?? "tool";
              return <ToolChip key={idx} label={name} />;
            })}
          </div>
        ) : null}
        {message.citations?.length ? <CitationStrip cites={message.citations} /> : null}
      </div>
    </div>
  );
}

function StreamingBubble({ state }: { state: StreamingState }) {
  return (
    <div className="flex flex-row gap-2.5">
      <Avatar isUser={false} userInitials="" />
      <div className="max-w-[85%] rounded-2xl border border-border bg-card/60 px-3.5 py-2.5 text-sm">
        {state.buffer ? <MessageBody content={state.buffer} /> : <TypingDots />}
        {state.toolEvents.length > 0 ? (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {state.toolEvents.map((ev, idx) => (
              <ToolChip
                key={idx}
                label={ev.kind === "start" ? `calling ${ev.name}…` : ev.summary}
              />
            ))}
          </div>
        ) : null}
        {state.citations.length ? <CitationStrip cites={state.citations} /> : null}
      </div>
    </div>
  );
}

function TypingDots() {
  return (
    <span className="inline-flex items-center gap-1 py-1">
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.3s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground [animation-delay:-0.15s]" />
      <span className="h-1.5 w-1.5 animate-bounce rounded-full bg-muted-foreground" />
    </span>
  );
}

function CitationStrip({ cites }: { cites: ChatCitation[] }) {
  // dedupe by file_path + line range
  const unique = useMemo(() => {
    const seen = new Set<string>();
    return cites.filter((c) => {
      const k = `${c.repository_id}:${c.file_path}:${c.start_line}-${c.end_line}`;
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
  }, [cites]);
  if (!unique.length) return null;
  return (
    <div className="mt-2.5 flex flex-wrap gap-1.5">
      {unique.map((c, idx) => (
        <Link
          key={idx}
          to={`/repositories/${c.repository_id}`}
          className="inline-flex items-center gap-1 rounded-md border border-border bg-card/60 px-2 py-0.5 font-mono text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          title={`${c.file_path}:${c.start_line}-${c.end_line}`}
        >
          <Quote className="h-3 w-3 text-primary" />
          <span>
            {c.file_path}:{c.start_line}-{c.end_line}
          </span>
        </Link>
      ))}
    </div>
  );
}

// Full markdown rendering (headings, lists, tables via remark-gfm). Fenced code
// blocks are routed through our syntax-highlighted CodeBlock; inline code is
// styled lightly. The `prose` classes come from @tailwindcss/typography.
const MARKDOWN_COMPONENTS: Components = {
  code({ className, children }) {
    const match = /language-(\w+)/.exec(className || "");
    const text = String(children ?? "").replace(/\n$/, "");
    if (match || text.includes("\n")) {
      return <CodeBlock lang={match?.[1] ?? "plaintext"} text={text} />;
    }
    return (
      <code className="rounded bg-muted/60 px-1 py-0.5 font-mono text-[0.85em]">
        {children}
      </code>
    );
  },
  // CodeBlock supplies its own wrapper; drop react-markdown's default <pre>.
  pre({ children }) {
    return <>{children}</>;
  },
  a({ children, href }) {
    return (
      <a
        href={href}
        target="_blank"
        rel="noreferrer"
        className="text-primary hover:underline"
      >
        {children}
      </a>
    );
  },
};

function MessageBody({ content }: { content: string }) {
  return (
    <div className="prose prose-invert prose-sm max-w-none break-words prose-p:my-1.5 prose-headings:mb-1.5 prose-headings:mt-3 prose-ul:my-1.5 prose-ol:my-1.5 prose-pre:my-2 prose-pre:bg-transparent prose-pre:p-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={MARKDOWN_COMPONENTS}>
        {content}
      </ReactMarkdown>
    </div>
  );
}

function CodeBlock({ lang, text }: { lang: string; text: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // clipboard may be unavailable on non-https; ignore
    }
  }

  return (
    <div className="overflow-hidden rounded-lg border border-border">
      <div className="flex items-center justify-between bg-muted/40 px-3 py-1 text-xs text-muted-foreground">
        <span className="font-mono">{lang || "code"}</span>
        <button
          onClick={copy}
          className="inline-flex items-center gap-1 transition-colors hover:text-foreground"
          title="Copy code"
        >
          {copied ? (
            <>
              <Check className="h-3 w-3" /> copied
            </>
          ) : (
            <>
              <Copy className="h-3 w-3" /> copy
            </>
          )}
        </button>
      </div>
      <SyntaxHighlighter
        language={lang}
        style={vscDarkPlus}
        wrapLongLines
        customStyle={{
          margin: 0,
          fontSize: "0.75rem",
          background: "rgb(30, 30, 30)",
        }}
        codeTagProps={{ style: { fontFamily: "ui-monospace, monospace" } }}
      >
        {text}
      </SyntaxHighlighter>
    </div>
  );
}

// silence unused-import warning when ApiError isn't surfaced in this file's signatures
void ApiError;
