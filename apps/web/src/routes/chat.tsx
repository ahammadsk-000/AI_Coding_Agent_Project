import { useEffect, useMemo, useRef, useState, type FormEvent } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams, Link } from "react-router-dom";
import { Plus, Send, Trash2, Wrench, Quote, Square, Copy, Check, Pencil } from "lucide-react";
import { Prism as SyntaxHighlighter } from "react-syntax-highlighter";
import { vscDarkPlus } from "react-syntax-highlighter/dist/esm/styles/prism";

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

export function ChatPage() {
  const { id } = useParams<{ id?: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();

  const { data: conversations } = useQuery({
    queryKey: ["conversations"],
    queryFn: api.listConversations,
    refetchInterval: 10_000,
  });

  const createConv = useMutation({
    mutationFn: () => api.createConversation({}),
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
    <div className="grid grid-cols-[18rem_1fr] gap-4 h-[calc(100vh-3rem)]">
      <aside className="border border-border rounded-lg bg-card/40 flex flex-col overflow-hidden">
        <div className="flex items-center justify-between p-3 border-b border-border">
          <span className="text-sm font-medium">Conversations</span>
          <Button size="sm" variant="outline" onClick={() => createConv.mutate()}>
            <Plus className="h-4 w-4 mr-1" /> New
          </Button>
        </div>
        <div className="flex-1 overflow-auto p-2 space-y-1">
          {(conversations ?? []).length === 0 ? (
            <div className="text-xs text-muted-foreground p-3">
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

      <section className="flex flex-col min-w-0">
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
      className={
        "rounded-md group flex items-center gap-2 px-2 py-1.5 text-sm " +
        (active
          ? "bg-accent text-accent-foreground"
          : "text-muted-foreground hover:bg-accent/50 hover:text-foreground")
      }
    >
      <Link to={`/chat/${conv.id}`} className="flex-1 min-w-0">
        <div className="truncate">{conv.title}</div>
        {conv.last_message_preview ? (
          <div className="truncate text-xs text-muted-foreground">
            {conv.last_message_preview}
          </div>
        ) : (
          <div className="text-xs text-muted-foreground">
            {conv.llm_provider} · {conv.llm_model}
          </div>
        )}
      </Link>
      <button
        onClick={(e) => {
          e.preventDefault();
          if (confirm(`Delete "${conv.title}"?`)) onDelete();
        }}
        className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-destructive"
        title="Delete"
      >
        <Trash2 className="h-3.5 w-3.5" />
      </button>
    </div>
  );
}

function EmptyChat({ onNew }: { onNew: () => void }) {
  return (
    <div className="flex-1 flex items-center justify-center text-center">
      <div className="space-y-3 max-w-md">
        <h2 className="text-xl font-semibold">Chat with your code</h2>
        <p className="text-sm text-muted-foreground">
          Ask questions about any of your ingested repositories. The agent will
          retrieve relevant code, optionally call read-only tools, and stream
          its answer with citations.
        </p>
        <Button onClick={onNew}>
          <Plus className="h-4 w-4 mr-1" /> Start a new chat
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
    <div className="flex flex-col min-h-0 h-full">
      <ChatHeader
        conversationId={conversationId}
        title={data.conversation.title}
        provider={data.conversation.llm_provider}
        model={data.conversation.llm_model}
      />

      <div className="flex-1 overflow-auto py-4 space-y-4">
        {data.messages
          .filter((m) => m.role !== "system" && m.role !== "tool")
          .map((m) => (
            <MessageBubble key={m.id} message={m} />
          ))}
        {streaming ? <StreamingBubble state={streaming} /> : null}
        {error ? (
          <div className="text-xs text-destructive">{error}</div>
        ) : null}
        <div ref={bottomRef} />
      </div>

      <form
        onSubmit={handleSubmit}
        className="border-t border-border pt-3 flex gap-2 items-end"
      >
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          rows={2}
          placeholder="Ask about your code — try 'What does index.html do?'"
          className="flex-1 resize-none rounded-md bg-card border border-border px-3 py-2 text-sm focus:outline-none focus:ring-1 focus:ring-primary"
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
            <Square className="h-4 w-4 mr-1" />
            Stop
          </Button>
        ) : (
          <Button type="submit" disabled={!input.trim()}>
            <Send className="h-4 w-4 mr-1" />
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
    <header className="px-1 pb-3 border-b border-border">
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
          className="text-sm font-semibold bg-card border border-border rounded px-2 py-1 w-full max-w-md focus:outline-none focus:ring-1 focus:ring-primary"
        />
      ) : (
        <div className="flex items-center gap-2 group">
          <span className="text-sm font-semibold truncate">{title}</span>
          <button
            onClick={() => {
              setDraft(title);
              setEditing(true);
            }}
            className="opacity-0 group-hover:opacity-100 text-muted-foreground hover:text-foreground"
            title="Rename"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        </div>
      )}
      <div className="text-xs text-muted-foreground">
        {provider} · {model}
      </div>
    </header>
  );
}

function MessageBubble({ message }: { message: ChatMessage }) {
  const isUser = message.role === "user";
  return (
    <div className={"flex " + (isUser ? "justify-end" : "justify-start")}>
      <div
        className={
          "max-w-[88%] rounded-lg px-3 py-2 text-sm whitespace-pre-wrap " +
          (isUser
            ? "bg-primary/20 text-foreground"
            : "bg-card border border-border")
        }
      >
        <MessageBody content={message.content} />
        {message.tool_calls?.length ? (
          <div className="mt-2 space-y-1">
            {message.tool_calls.map((tc, idx) => {
              const name = (tc as { function?: { name?: string } }).function?.name ?? "tool";
              return (
                <div
                  key={idx}
                  className="text-xs text-muted-foreground flex items-center gap-1"
                >
                  <Wrench className="h-3 w-3" /> called <code>{name}</code>
                </div>
              );
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
    <div className="flex justify-start">
      <div className="max-w-[88%] rounded-lg px-3 py-2 text-sm bg-card border border-border whitespace-pre-wrap">
        <MessageBody content={state.buffer || "…"} />
        {state.toolEvents.length > 0 ? (
          <div className="mt-2 space-y-0.5">
            {state.toolEvents.map((ev, idx) => (
              <div
                key={idx}
                className="text-xs text-muted-foreground flex items-center gap-1"
              >
                <Wrench className="h-3 w-3" />
                {ev.kind === "start"
                  ? `calling ${ev.name}…`
                  : ev.summary}
              </div>
            ))}
          </div>
        ) : null}
        {state.citations.length ? <CitationStrip cites={state.citations} /> : null}
      </div>
    </div>
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
    <div className="mt-2 flex flex-wrap gap-1">
      {unique.map((c, idx) => (
        <Link
          key={idx}
          to={`/repositories/${c.repository_id}`}
          className="inline-flex items-center gap-1 text-xs px-1.5 py-0.5 rounded bg-muted/40 hover:bg-muted text-muted-foreground hover:text-foreground"
          title={`${c.file_path}:${c.start_line}-${c.end_line}`}
        >
          <Quote className="h-3 w-3" />
          <span className="font-mono">
            {c.file_path}:{c.start_line}-{c.end_line}
          </span>
        </Link>
      ))}
    </div>
  );
}

// Markdown-lite renderer: extract fenced ```lang code blocks and pass them
// through SyntaxHighlighter; everything else as plain text.
const CODE_FENCE_RE = /```([a-zA-Z0-9_+-]*)\n([\s\S]*?)```/g;

function MessageBody({ content }: { content: string }) {
  const parts = useMemo(() => {
    const result: Array<
      | { kind: "text"; text: string }
      | { kind: "code"; lang: string; text: string }
    > = [];
    let lastIndex = 0;
    for (const match of content.matchAll(CODE_FENCE_RE)) {
      const [full = "", lang = "", code = ""] = match;
      const start = match.index ?? 0;
      if (start > lastIndex) {
        result.push({ kind: "text", text: content.slice(lastIndex, start) });
      }
      result.push({ kind: "code", lang: lang || "plaintext", text: code });
      lastIndex = start + full.length;
    }
    if (lastIndex < content.length) {
      result.push({ kind: "text", text: content.slice(lastIndex) });
    }
    return result;
  }, [content]);

  const only = parts[0];
  if (parts.length === 1 && only && only.kind === "text") {
    return <>{only.text}</>;
  }
  return (
    <div className="space-y-2">
      {parts.map((p, idx) =>
        p.kind === "text" ? (
          <span key={idx}>{p.text}</span>
        ) : (
          <CodeBlock key={idx} lang={p.lang} text={p.text} />
        ),
      )}
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
    <div className="relative group/code">
      <button
        onClick={copy}
        className="absolute top-1 right-1 z-10 opacity-0 group-hover/code:opacity-100 rounded bg-black/40 hover:bg-black/60 p-1 text-xs text-muted-foreground"
        title="Copy code"
      >
        {copied ? <Check className="h-3.5 w-3.5" /> : <Copy className="h-3.5 w-3.5" />}
      </button>
      <SyntaxHighlighter
        language={lang}
        style={vscDarkPlus}
        wrapLongLines
        customStyle={{
          margin: 0,
          fontSize: "0.75rem",
          borderRadius: "0.375rem",
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
