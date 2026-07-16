# MCP Server — expose your indexed code over the Model Context Protocol

The **Model Context Protocol (MCP)** is an open standard that lets any AI host
(Claude Desktop, IDEs, other agents) connect to external tools and data through a
uniform interface. This project ships a small **MCP server** that turns your
ingested repositories into MCP tools, so an MCP host can search and read your code.

The server is a thin client over the REST API ([apps/api/app/mcp_server.py](../apps/api/app/mcp_server.py)),
so it works against your **live deployment** or a local one. It is not part of the
web/worker runtime — you run it on demand as a local process (stdio transport).

## Tools it exposes

| Tool | What it does |
|------|--------------|
| `list_repositories()` | List your ingested repos + status. |
| `search_code(query, k=5)` | Hybrid (semantic + keyword) search over your indexed code. |
| `read_file(repository_name, file_path)` | Read a file's full content by repo name + path. |

## Run it

```bash
pip install fastmcp httpx

export ACA_API_URL=https://your-api.onrender.com   # or http://localhost:8000
export ACA_EMAIL=you@example.com
export ACA_PASSWORD=your-password

cd apps/api
python -m app.mcp_server
```

The server authenticates once (login → JWT), caches the token, and serves tool
calls over stdio.

## Register it with Claude Desktop

Add this to your Claude Desktop MCP config
(`claude_desktop_config.json` → *Settings → Developer → Edit Config*):

```json
{
  "mcpServers": {
    "ai-coding-agent": {
      "command": "python",
      "args": ["-m", "app.mcp_server"],
      "cwd": "/absolute/path/to/AI_Coding_Agent_Project/apps/api",
      "env": {
        "ACA_API_URL": "https://your-api.onrender.com",
        "ACA_EMAIL": "you@example.com",
        "ACA_PASSWORD": "your-password"
      }
    }
  }
}
```

Restart Claude Desktop. You'll then be able to ask it things like
*"search my code for how command groups are registered"* and it will call
`search_code` on your indexed repositories.

## How it fits the architecture

```
MCP host (Claude Desktop / IDE)
        │  MCP (stdio)
        ▼
app.mcp_server  (FastMCP)
        │  REST + JWT
        ▼
FastAPI backend  →  hybrid search (Qdrant + Postgres)  →  your indexed repos
```

> **Security note:** the server logs in with the credentials you provide via env
> vars and acts as that user. Keep the config file private; prefer a dedicated,
> least-privileged account. For a shared setup, swap password auth for a
> pre-issued access token.
