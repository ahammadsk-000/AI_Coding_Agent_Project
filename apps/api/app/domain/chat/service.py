"""Chat service: agent loop with RAG context injection + tool calling + streaming.

This is a *single-pass* agent (no LangGraph yet — that's a follow-up). The loop:

1. Caller supplies a user message and a conversation.
2. We pull relevant code via Phase-3 hybrid search (`context_builder`) and
   format it into a system-prompt prelude. Cap at `_RAG_TOKEN_BUDGET` tokens.
3. We construct the message history (system + history + new user msg) and call
   the configured LLM with the safe tool definitions exposed.
4. If the LLM emits tool_calls, we execute them, append tool result messages,
   and call the LLM again. Loop up to `_MAX_TOOL_ROUNDS` times.
5. We persist every message (including tool messages) to Postgres so the
   conversation is fully replayable.
6. When streaming, every token + tool_call event is published to a consumer
   queue so the WebSocket layer can forward to the client in real time.

The service never imports FastAPI — transport is plumbed in
`app/api/v1/chat.py`.
"""
from __future__ import annotations

import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, AsyncIterator
from uuid import UUID

from app.core.config import settings
from app.core import metrics as M
from app.core.cost import count_message_tokens, count_tokens, estimate_cost_usd
from app.core.exceptions import ConflictError, NotFoundError
from app.core.logging import get_logger
from app.domain.chat.models import Conversation, Message, MessageRole
from app.domain.chat.repository import ConversationRepo, MessageRepo
from app.domain.chat.schemas import (
    ConversationCreate,
    WsCitations,
    WsDone,
    WsError,
    WsToken,
    WsToolCallResult,
    WsToolCallStart,
)
from app.domain.chat.tools import TOOL_DEFS, execute_tool
from app.domain.memory.models import MemoryScope, MemorySource
from app.domain.memory.service import MemoryService
from app.domain.search.context import pack_context
from app.domain.search.service import SearchService
from app.domain.users.models import User
from app.infrastructure.llm import (
    ChatMessage,
    StreamChunk,
    ToolCall,
    get_llm_provider,
)
from sqlalchemy.ext.asyncio import AsyncSession

log = get_logger("chat")

_RAG_TOKEN_BUDGET = 1500
_MAX_TOOL_ROUNDS = 5

# Tools are powerful but require the LLM to reliably emit structured tool_calls
# AND synthesize tool results back into a coherent answer. Small open-weights
# models (≤2B params) frequently fail one or both steps. Models ≥3B (Llama 3.2
# latest, Mistral 7B, OpenAI) handle tools well enough for production use.
#
# We default to enabled; `_tools_for_provider` below downgrades automatically
# for known-too-small Ollama models even when the global flag is on.
_TOOLS_ENABLED_DEFAULT = True


def _tools_for_provider(provider_name: str, model_name: str) -> bool:
    """Decide whether to expose tools to this provider+model combo."""
    if not _TOOLS_ENABLED_DEFAULT:
        return False
    # Heuristic fallback: avoid tools on known-small Ollama models.
    if provider_name == "ollama":
        lo = (model_name or "").lower()
        if any(tag in lo for tag in (":1b", "-1b", ":1.5b", ":0.5b")):
            return False
    return True

_SYSTEM_PROMPT_TEMPLATE = """\
You are a friendly, helpful AI coding assistant. You can both chat naturally
and answer questions about the user's ingested git repositories.

HOW TO DECIDE WHAT KIND OF TURN THIS IS:

- If the user's message is conversational — a greeting, thanks, an
  acknowledgment, small talk, or a general non-code question — reply briefly
  and warmly in one or two sentences. Do NOT call any tools. Do NOT say
  things like "I don't see that in your ingested code" — they didn't ask
  about code. Match their tone; if they're casual, be casual.

- If the user's message is a code or repository question (about files,
  functions, classes, structure, "what does X do", "find Y", "show me Z",
  etc.) then ground your answer in:
    (a) the repository/file inventory in the section above, AND
    (b) the "Relevant code" block below.
  Cite using `file_path:start-end` format with the EXACT path from those
  sections. Never invent file paths, function names, class names, or line
  numbers; placeholder strings like `path/to/file.py` are forbidden.

- If the "Relevant code" block contains code related to the question, USE IT:
  summarize and explain what you see, and cite it. Do this EVEN WHEN the user
  refers to a repository by a name that doesn't exactly match the inventory —
  the user may use the GitHub/clone name while the inventory shows a different
  display name, and there is often only one repository in scope. NEVER refuse
  to answer just because a repository name doesn't match.

- For "what does this repository do" questions, give a short overview from the
  file inventory and the retrieved code (the key files, languages, and apparent
  purpose). Describe what you actually see rather than refusing.

- Only say "I don't see that in your ingested code" when the "Relevant code"
  block is empty or clearly unrelated to the question — never when relevant
  code was actually retrieved.

CODE QUOTING — read carefully:

- When you quote code, COPY IT VERBATIM from the "Relevant code" block.
  Do NOT invent code that "looks plausible". If the block does not contain a
  function the user asked about, DO NOT write a stub or example version of
  that function. Say you don't have it.

- Fenced code blocks in your reply must contain only text that appears in the
  context above. If you need to explain something the context doesn't show,
  describe it in prose without writing fake code.

- Be concise. Short and accurate beats long and speculative.

{memory_block}

{repo_blurb}

{rag_context}
"""

_NO_CONTEXT_NOTE = (
    "# Relevant code from the user's repositories\n"
    "(no matching code was retrieved for this query — answer from the user's "
    "message alone; if they're asking about their code, tell them you couldn't "
    "find anything relevant in the ingested repositories.)"
)

# Short conversational turns bypass the (slow) RAG search + tool offering.
# Misses fall through to the full code path — the unified system prompt still
# tells the model to reply naturally, so false negatives just cost a little
# latency, not correctness.
import re as _re

_CHIT_CHAT_PATTERNS = [
    _re.compile(p, _re.IGNORECASE)
    for p in (
        # greetings
        r"^\s*(hi|hello|hey|yo|hola|sup|howdy)\b.*$",
        # acknowledgments / agreement
        r"^\s*(yeah|yes|yep|yup|yea|nah|nope|sure|ok|okay|right|alright|"
        r"got it|i see|makes sense|fair enough|sounds good|exactly|"
        r"true|cool|nice|great|awesome|cheers)\b.*$",
        # thanks / sign-off
        r"^\s*(thanks|thank you|ty|cool thanks|appreciate it|"
        r"bye|goodbye|see ya|see you|later|talk later)\b.*$",
        # "how are you" style
        r"^\s*how\s+(are\s+you|('?s| is)\s+it\s+going|are\s+things)\b.*$",
        # short positive replies
        r"^\s*(i'?m|i am|im)\s+(good|great|fine|well|doing\s+(good|great|fine|well))\b.*$",
        # request to continue chat
        r"^\s*(go on|tell me more|continue|keep going|and\??|anything else\??)\s*$",
    )
]


def _looks_like_greeting(text: str) -> bool:
    """Detect conversational chit-chat. Keep patterns short and high-precision.

    Code-related keywords ("code", "file", "function", "class", "search",
    "find", "show", "what does", "implement") override the match so we don't
    accidentally swallow real questions.
    """
    s = text.strip()
    if not s or len(s) > 100:
        return False
    lowered = s.lower()
    # Hard veto: any clear code-question marker pushes through to the code path
    code_markers = (
        "code", "file", "function", "class", "method", "implement",
        "what does ", "how does ", "show me ", "search ", "find ",
        "explain ", "describe ", "review ",
    )
    if any(marker in lowered for marker in code_markers):
        return False
    return any(p.match(s) for p in _CHIT_CHAT_PATTERNS)


# Heuristic: small models sometimes write a tool call as text instead of
# emitting a structured tool_calls event. We only flag the obvious leak
# patterns where the model's *response* literally starts with a function-call
# template — those answers are useless to the user regardless. Anything more
# permissive false-positives on legitimate prose that happens to mention
# `function`, `parameters`, etc.
_LEAK_STARTERS = (
    "{function ",
    "{function:",
    "{\"function\"",
    "<function ",
    "<function=",
    "<|function_call|>",
    "function ",
    "<tool_call>",
    "<tool_call ",
)


def _looks_like_leaked_tool_call(text: str) -> bool:
    if not text:
        return False
    s = text.strip().lstrip("`").lstrip()
    return any(s.startswith(p) for p in _LEAK_STARTERS)


# Explicit "remember this" cues. When a user message starts with one of these,
# we store the remainder as a durable memory (in addition to answering).
_MEMORY_CUES = [
    _re.compile(p, _re.IGNORECASE)
    for p in (
        r"^\s*(?:please\s+)?remember(?:\s+that)?\s*[:,]?\s+(.+)$",
        r"^\s*(?:please\s+)?note(?:\s+that)?\s*[:,]?\s+(.+)$",
        r"^\s*keep in mind(?:\s+that)?\s*[:,]?\s+(.+)$",
        r"^\s*(?:for future reference|fyi)\s*[:,]?\s+(.+)$",
        r"^\s*don'?t forget(?:\s+that)?\s*[:,]?\s+(.+)$",
    )
]


def _extract_memory_cue(text: str) -> str | None:
    """If the message is an explicit 'remember X', return the fact X, else None."""
    s = text.strip()
    for p in _MEMORY_CUES:
        m = p.match(s)
        if m:
            fact = m.group(1).strip().rstrip(".")
            if len(fact) >= 3:
                return fact
    return None


def _sanitize_history(messages: list[Message]) -> list[Message]:
    """Filter history to a shape every LLM provider can consume safely.

    Drops:
      - `tool` role messages — they require a matched assistant `tool_calls`
        preceding them; mismatches make Ollama / OpenAI both reject the call.
      - `assistant` messages with empty content — these are pure tool-call
        invocations that didn't produce a textual reply (often from interrupted
        agent rounds in earlier broken conversations).
    """
    out: list[Message] = []
    for m in messages:
        if m.role == MessageRole.tool:
            continue
        if m.role == MessageRole.assistant and not (m.content or "").strip():
            continue
        out.append(m)
    return out


@dataclass(slots=True)
class _AgentEvent:
    """Internal queue item for streaming events back to the WS layer."""
    payload: Any   # Pydantic WS* model


class ChatService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.conv_repo = ConversationRepo(session)
        self.msg_repo = MessageRepo(session)
        self.memory = MemoryService(session)

    # ---------- conversation CRUD ----------

    async def create_conversation(
        self, owner: User, data: ConversationCreate
    ) -> Conversation:
        provider = (data.llm_provider or settings.llm_provider).lower()
        if provider == "ollama":
            model = data.llm_model or settings.ollama_default_model
        elif provider == "openai":
            model = data.llm_model or settings.openai_default_model
        else:
            model = data.llm_model or settings.ollama_default_model
            provider = "ollama"
        conv = Conversation(
            owner_id=owner.id,
            title=data.title or "New chat",
            repository_ids=[str(r) for r in data.repository_ids],
            llm_provider=provider,
            llm_model=model,
        )
        return await self.conv_repo.add(conv)

    async def list_conversations(
        self, owner: User
    ) -> list[tuple[Conversation, int, str | None]]:
        return await self.conv_repo.list_for_owner(owner.id)

    async def get_conversation(self, owner: User, conv_id: UUID) -> Conversation:
        conv = await self.conv_repo.get_for_owner(conv_id, owner.id)
        if conv is None:
            raise NotFoundError("Conversation not found")
        return conv

    async def get_messages(self, owner: User, conv_id: UUID) -> list[Message]:
        await self.get_conversation(owner, conv_id)  # auth check
        return await self.msg_repo.list_for_conversation(conv_id)

    async def delete_conversation(self, owner: User, conv_id: UUID) -> None:
        conv = await self.get_conversation(owner, conv_id)
        await self.conv_repo.delete(conv)

    async def rename_conversation(
        self, owner: User, conv_id: UUID, title: str
    ) -> Conversation:
        conv = await self.get_conversation(owner, conv_id)
        conv.title = title.strip()[:255] or conv.title
        await self.session.flush()
        await self.session.commit()
        return conv

    # ---------- agent loop ----------

    async def send_message_streaming(
        self, owner: User, conv_id: UUID, user_text: str
    ) -> AsyncIterator[Any]:
        """Append a user message and stream the assistant's reply.

        Yields Pydantic WS* events for the WebSocket layer to serialize. Persists
        every message produced (user, assistant, tool) to Postgres.
        """
        conv = await self.get_conversation(owner, conv_id)
        if not user_text.strip():
            raise ConflictError("message cannot be empty")

        # 1. persist the user's message
        user_msg = Message(
            conversation_id=conv.id,
            role=MessageRole.user,
            content=user_text,
            token_count=count_tokens(user_text),
        )
        await self.msg_repo.add(user_msg)
        M.chat_messages_total.labels("user").inc()
        await self.conv_repo.touch(conv)
        # If this is the very first user message and the title is still default,
        # auto-title from the first ~50 chars.
        if conv.title in ("", "New chat"):
            conv.title = user_text.strip().splitlines()[0][:80] or "New chat"
        await self.session.commit()

        # 1b. explicit memory capture: if the user said "remember X", store the
        # fact so it can be recalled in future conversations.
        memory_captured: str | None = None
        fact = _extract_memory_cue(user_text)
        if fact is not None:
            repo_ids_for_scope = [UUID(r) for r in (conv.repository_ids or [])]
            scope = MemoryScope.project if repo_ids_for_scope else MemoryScope.user
            await self.memory.remember(
                owner,
                content=fact,
                scope=scope,
                repository_id=repo_ids_for_scope[0] if repo_ids_for_scope else None,
                conversation_id=conv.id,
                source=MemorySource.explicit,
                importance=0.8,
            )
            await self.session.commit()
            memory_captured = fact

        # 2. build the message list to send to the LLM. Same system prompt for
        # all turns — the model decides whether to chat or ground in code based
        # on what the user actually said. Chit-chat detection only controls
        # performance optimizations: skip the (expensive) RAG search + don't
        # offer tools when the message is clearly conversational.
        is_chit_chat = _looks_like_greeting(user_text)
        repo_blurb = await self._repo_blurb_async(owner, conv)
        if is_chit_chat:
            rag_block = (
                "# Relevant code from the user's repositories\n"
                "(retrieval skipped: this turn looks conversational; "
                "no code lookup performed)"
            )
            rag_citations: list[dict[str, Any]] = []
        else:
            rag_block, rag_citations = await self._build_rag_context(
                owner, conv, user_text
            )

        # Recall durable memories relevant to this turn and fold them into the
        # system prompt so the agent "remembers" across conversations.
        memory_block = await self._build_memory_block(
            owner, conv, user_text, just_saved=memory_captured
        )

        system_prompt = _SYSTEM_PROMPT_TEMPLATE.format(
            memory_block=memory_block, repo_blurb=repo_blurb, rag_context=rag_block
        )

        prior_history = await self.msg_repo.list_for_conversation(conv.id)
        # `prior_history` already includes the just-saved user message.
        llm_messages: list[ChatMessage] = [
            ChatMessage(role="system", content=system_prompt)
        ]
        for m in _sanitize_history(prior_history):
            llm_messages.append(
                ChatMessage(
                    role=m.role.value,   # type: ignore[arg-type]
                    content=m.content,
                    # Strip tool_calls from history. Re-driving tool-call state
                    # across providers (Ollama vs OpenAI vs no-tools fallback)
                    # is fragile; the current-round agent loop already manages
                    # tool execution. History only needs the text turns.
                    tool_calls=None,
                    tool_call_id=None,
                )
            )

        if rag_citations:
            yield WsCitations(citations=rag_citations)

        # 3. agent loop — drive the LLM and execute tool calls until it stops
        provider_obj = get_llm_provider(provider=conv.llm_provider, model=conv.llm_model)
        # Tools are disabled by default (see _TOOLS_ENABLED_DEFAULT above) and
        # always disabled for chit-chat. The RAG context block + pre-loaded
        # file inventory in the system prompt cover the common cases without
        # needing the agent loop.
        provider_uses_tools = _tools_for_provider(conv.llm_provider, conv.llm_model)
        tools_for_round: list = (
            TOOL_DEFS if provider_uses_tools and not is_chit_chat else []
        )

        rounds = 0
        accumulated_text = ""
        last_tool_calls: list[ToolCall] = []
        final_citations: list[dict[str, Any]] = list(rag_citations)

        while True:
            rounds += 1
            accumulated_text = ""
            last_tool_calls = []
            # --- metrics: prompt tokens + latency timer for this LLM round ---
            prompt_tokens = count_message_tokens(
                [{"role": m.role, "content": m.content} for m in llm_messages]
            )
            _llm_started = time.perf_counter()
            try:
                async for chunk in provider_obj.stream(
                    llm_messages,
                    tools=tools_for_round or None,
                    temperature=0.2,
                ):
                    if chunk.text_delta:
                        accumulated_text += chunk.text_delta
                        yield WsToken(delta=chunk.text_delta)
                    if chunk.tool_calls:
                        last_tool_calls = chunk.tool_calls
            except Exception as exc:
                err = f"{type(exc).__name__}: {exc}"
                log.error("llm_stream_failed", error=err, provider=conv.llm_provider)
                M.llm_requests_total.labels(
                    conv.llm_provider, conv.llm_model, "error"
                ).inc()
                yield WsError(message=f"LLM call failed: {err}")
                return

            # --- metrics: record tokens, latency, cost for this round ---
            completion_tokens = count_tokens(accumulated_text)
            elapsed = time.perf_counter() - _llm_started
            M.llm_requests_total.labels(conv.llm_provider, conv.llm_model, "ok").inc()
            M.llm_request_duration_seconds.labels(
                conv.llm_provider, conv.llm_model
            ).observe(elapsed)
            M.llm_tokens_total.labels(
                conv.llm_provider, conv.llm_model, "prompt"
            ).inc(prompt_tokens)
            M.llm_tokens_total.labels(
                conv.llm_provider, conv.llm_model, "completion"
            ).inc(completion_tokens)
            _cost = estimate_cost_usd(conv.llm_model, prompt_tokens, completion_tokens)
            if _cost > 0:
                M.llm_cost_usd_total.labels(conv.llm_provider, conv.llm_model).inc(_cost)

            # Persist whatever the assistant emitted on this round.
            assistant_msg = Message(
                conversation_id=conv.id,
                role=MessageRole.assistant,
                content=accumulated_text,
                tool_calls=[
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in last_tool_calls
                ]
                or None,
                citations=final_citations or None,
                token_count=completion_tokens,
            )
            await self.msg_repo.add(assistant_msg)
            await self.session.commit()
            M.chat_messages_total.labels("assistant").inc()
            llm_messages.append(
                ChatMessage(
                    role="assistant",
                    content=accumulated_text,
                    tool_calls=assistant_msg.tool_calls,
                )
            )

            # No tool calls → we're done, unless the model leaked a tool call
            # as plain text (a small-model failure mode). In that case, replace
            # the message content with a clear apology so the UI doesn't show
            # the garbled schema.
            if not last_tool_calls:
                if _looks_like_leaked_tool_call(accumulated_text):
                    fallback = (
                        "(The model tried to call a tool but wrote it out as "
                        "text instead of invoking it. Could you rephrase the "
                        "question? For example: "
                        "\"list the files in test_repo\" → "
                        "\"what files are in test_repo?\")"
                    )
                    assistant_msg.content = fallback
                    await self.session.commit()
                    # Stream the fallback so the UI shows something useful in
                    # place of the garbled schema text it just received.
                    yield WsToken(delta="\n\n" + fallback)
                yield WsDone(message_id=assistant_msg.id)
                return

            if rounds >= _MAX_TOOL_ROUNDS:
                yield WsError(
                    message=f"agent stopped after {_MAX_TOOL_ROUNDS} tool rounds"
                )
                return

            # Run each tool, persist its result, feed back into llm_messages.
            for tc in last_tool_calls:
                yield WsToolCallStart(name=tc.name, arguments=tc.arguments, call_id=tc.id)
                try:
                    result, summary, tc_citations = await execute_tool(
                        tc.name, tc.arguments, user=owner, session=self.session
                    )
                    tool_status = "error" if isinstance(result, dict) and result.get("error") else "ok"
                    M.tool_calls_total.labels(tc.name, tool_status).inc()
                except Exception as exc:
                    summary = f"{tc.name} raised {type(exc).__name__}: {exc}"
                    result = {"error": str(exc)}
                    tc_citations = []
                    M.tool_calls_total.labels(tc.name, "error").inc()

                yield WsToolCallResult(call_id=tc.id, summary=summary)
                if tc_citations:
                    final_citations.extend(tc_citations)
                    yield WsCitations(citations=tc_citations)

                tool_msg = Message(
                    conversation_id=conv.id,
                    role=MessageRole.tool,
                    content=json.dumps(result)[:32_000],   # cap tool payload size
                    tool_call_id=tc.id,
                )
                await self.msg_repo.add(tool_msg)
                M.chat_messages_total.labels("tool").inc()
                llm_messages.append(
                    ChatMessage(
                        role="tool",
                        content=tool_msg.content,
                        tool_call_id=tc.id,
                    )
                )
            await self.session.commit()
            # Loop back for the next LLM round.

    # ---------- helpers ----------

    async def _build_rag_context(
        self, owner: User, conv: Conversation, query: str
    ) -> tuple[str, list[dict[str, Any]]]:
        """Pull relevant code via Phase-3 search and format as a system-prompt block.

        Always returns a non-empty marker so the model knows whether retrieval
        happened — empty strings let models hallucinate.
        """
        repo_ids = [UUID(r) for r in (conv.repository_ids or [])]
        if not repo_ids and not (await self._owner_has_repos(owner)):
            return (_NO_CONTEXT_NOTE, [])

        service = SearchService(self.session)
        hits, _reranked, _took = await service.search(
            owner,
            query=query,
            repository_ids=repo_ids,
            k=15,
            mode="hybrid",
            rerank=True,
        )
        if not hits:
            return (_NO_CONTEXT_NOTE, [])

        files, _total, _truncated = pack_context(hits, max_tokens=_RAG_TOKEN_BUDGET)
        if not files:
            return (_NO_CONTEXT_NOTE, [])

        lines: list[str] = ["# Relevant code from the user's repositories"]
        citations: list[dict[str, Any]] = []
        for f in files:
            for c in f.chunks:
                lines.append(
                    f"\n## {f.file_path}:{c.start_line}-{c.end_line} ({f.language or 'text'})"
                )
                lines.append("```" + (f.language or ""))
                lines.append(c.content)
                lines.append("```")
                citations.append(
                    {
                        "repository_id": str(c.repository_id),
                        "file_id": str(c.file_id),
                        "file_path": c.file_path,
                        "start_line": c.start_line,
                        "end_line": c.end_line,
                    }
                )
        return ("\n".join(lines), citations)

    async def _owner_has_repos(self, owner: User) -> bool:
        from app.domain.repositories.repository import RepositoryRepo

        repos = RepositoryRepo(self.session)
        return bool(await repos.list_for_owner(owner.id))

    async def _build_memory_block(
        self, owner: User, conv: Conversation, query: str, *, just_saved: str | None
    ) -> str:
        """Recall durable memories relevant to the turn → system-prompt section."""
        repo_ids = [UUID(r) for r in (conv.repository_ids or [])]
        try:
            recalled = await self.memory.recall(
                owner, query=query, repository_ids=repo_ids, k=5
            )
        except Exception:
            recalled = []

        lines: list[str] = ["# What you remember about this user"]
        if just_saved:
            lines.append(f"- (just saved this turn) {just_saved}")
        for r in recalled:
            # avoid duplicating the just-saved fact
            if just_saved and r.content.strip() == just_saved.strip():
                continue
            lines.append(f"- {r.content}")
        if len(lines) == 1:
            lines.append("(no stored memories relevant to this message)")
        lines.append(
            "\nUse these remembered facts naturally when relevant. If the user "
            "just asked you to remember something, briefly confirm you've noted it."
        )
        return "\n".join(lines)

    async def _repo_blurb_async(self, owner: User, conv: Conversation) -> str:
        """Name the repos + file inventory the model can see, so it can answer
        questions like "list the files in test_repo" without needing a tool
        call. Small models are unreliable at structured tool calls; preloading
        cheap factual context avoids the round trip entirely.
        """
        from app.domain.repositories.repository import RepositoryRepo
        from sqlalchemy import select
        from app.domain.repositories.models import RepositoryFile

        repos = RepositoryRepo(self.session)
        owned = await repos.list_for_owner(owner.id)
        if not owned:
            return "The user has NO ingested repositories yet. Tell them to ingest one first."
        scope_ids = set(conv.repository_ids or [])
        in_scope = (
            [r for r in owned if str(r.id) in scope_ids] if scope_ids else owned
        )
        if not in_scope:
            in_scope = owned

        # Per-repo inventory: at most 30 files each, sorted by path. Anything
        # bigger gets a "+N more" footer. This keeps the prompt bounded.
        _PER_REPO_FILE_CAP = 30
        sections: list[str] = []
        for r in in_scope:
            stmt = (
                select(RepositoryFile)
                .where(RepositoryFile.repository_id == r.id)
                .order_by(RepositoryFile.path)
            )
            files_rows = list((await self.session.execute(stmt)).scalars())
            if not files_rows:
                inv = "  (no files yet)"
            else:
                shown = files_rows[:_PER_REPO_FILE_CAP]
                extra = len(files_rows) - len(shown)
                lines = [
                    f"  - `{f.path}` ({f.language or 'text'}, {f.lines} lines)"
                    for f in shown
                ]
                if extra > 0:
                    lines.append(f"  - ... and {extra} more file(s)")
                inv = "\n".join(lines)
            sections.append(
                f"### `{r.name}` (default branch `{r.default_branch}`)\n{inv}"
            )

        return (
            "Available repositories and their files (use these names + paths "
            "VERBATIM in tool calls and citations; do not invent any):\n\n"
            + "\n\n".join(sections)
        )
