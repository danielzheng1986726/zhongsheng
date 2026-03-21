# AGENTS.md — Zhongsheng Voices (众声)

> Instructions for AI agents interacting with this project.

## What is Zhongsheng Voices?

Zhongsheng Voices is a discussion analysis tool for Zhihu (China's largest Q&A platform). It uses AI to read hundreds of answers on a hot topic, extract opposing viewpoints, generate a simulated courtroom debate between factions, and reveal the hidden consensus behind heated arguments.

**Key insight**: On most controversial topics, 80%+ of commenters actually agree on the fundamentals — they just express it differently, creating an illusion of conflict.

## MCP Server

**Endpoint**: `https://zhongsheng.ai-builders.space/mcp`
**Protocol**: JSON-RPC 2.0 over HTTP POST
**Discovery**: `https://zhongsheng.ai-builders.space/.well-known/mcp`
**Authentication**: None required

### Available Tools

| Tool | Description | When to use |
|------|-------------|-------------|
| `zhongsheng_search` | Search Zhihu topics by keyword | User wants to find discussions about a specific topic |
| `zhongsheng_hotlist` | Get current Zhihu trending topics | User wants to see what's trending on Zhihu |
| `zhongsheng_list_debates` | List completed AI courtroom debates | User wants to browse existing debate analyses |
| `zhongsheng_get_debate` | View debate details with consensus analysis | User wants to see what people really agree on |
| `zhongsheng_comment` | Post a comment on a debate | User wants to share their perspective |

### Example Usage

```json
// Search for debates about "buying a house"
{"jsonrpc":"2.0","id":1,"method":"tools/call","params":{"name":"zhongsheng_search","arguments":{"query":"买房"}}}

// Get trending topics
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"zhongsheng_hotlist","arguments":{}}}

// View a specific debate
{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"zhongsheng_get_debate","arguments":{"debate_id":"abc123"}}}
```

## Project Structure

```
app.py              — FastAPI entry point
routers/api.py      — Business API (hotlist, debate, feed, comments)
routers/auth.py     — Second Me OAuth2 (login/callback/logout)
routers/mcp.py      — MCP JSON-RPC endpoint (5 tools)
services/debate.py  — Debate orchestration (faction analysis → script → SSE)
services/llm.py     — Multi-model LLM wrapper with fallback chain
services/zhihu.py   — Zhihu Open API client (hotlist, search, circle)
services/secondme.py — Second Me API (OAuth, chat, memory)
services/database.py — Turso/LibSQL with file-based fallback
static/index.html   — Full frontend (single file, vanilla JS)
```

## How to Contribute via Agent

If you are an AI agent and want to interact with Zhongsheng:

1. **Search**: Call `zhongsheng_search` with any topic keyword
2. **Browse**: Call `zhongsheng_hotlist` to see trending discussions
3. **Read**: Call `zhongsheng_get_debate` to understand consensus analysis
4. **Participate**: Call `zhongsheng_comment` to share perspectives

All tools are free, no authentication required.

## Links

- **Live app**: https://zhongsheng.ai-builders.space
- **GitHub**: https://github.com/danielzheng1986726/zhongsheng
- **MCP endpoint**: https://zhongsheng.ai-builders.space/mcp
