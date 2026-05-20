# llama-skills

**Status:** Implemented (iteration 1)  
**Date:** 2026-05-20

## 1. Philosophy

Skills exist because system prompts have a cost. Loading every skill's full instructions into context on every request is wasteful; asking the model to discover skills via tool calls before every task is slow. The right answer is *progressive disclosure*: all skills are always known, but only the relevant one is loaded.

llama-skills implements exactly that split, and nothing else. It is thin middleware, not an agent framework. It does not run tool loops, orchestrate multi-step workflows, or execute skill content. It reads files and injects text. The model does the rest.

Two design principles flow from this:

**Skills are files.** llama-skills never interprets skill content. It reads YAML frontmatter for the registry and returns file bytes for retrieval. What a skill *says* is entirely between the skill author and the model.

**Each transport layer does one job.** The OpenAI-compatible proxy handles discovery — it costs nothing at inference time beyond the frontmatter tokens already in context. The MCP server handles activation — the model fetches the full skill body only when it decides the skill is relevant. This maps directly onto how llama-server's architecture already works: an HTTP API for inference, a browser-based MCP client for tools.

## 2. Background

The [Agent Skills open standard](https://agentskills.io/specification) (formalised December 2025) defines a portable, tool-agnostic format for LLM skills: a folder named after the skill, anchored by a `SKILL.md` file with YAML frontmatter and a Markdown body, with optional subdirectories for scripts, references, and assets. Claude Code, OpenAI Codex CLI, and similar CLI agents implement this natively via stdio.

llama-server (llama.cpp) is different. It runs as a persistent HTTP API server exposing an OpenAI-compatible `/v1/` endpoint. Its web UI ships a browser-side MCP client (`llama-webui-mcp`) that speaks Streamable HTTP — not stdio. The skills runtime built into CLI agents does not transfer here.

No existing tool bridges the Agent Skills standard to this architecture. The gap is:

- **Discovery:** no mechanism to inject skill frontmatter into llama-server requests at inference time
- **Activation:** no HTTP MCP server that exposes skill file content to the browser-side MCP client

llama-skills fills both gaps in a single service that runs alongside llama-server on your inference host.

## 3. Purpose

llama-skills makes the Agent Skills standard work with llama-server and its WebUI. It:

1. Scans a skills directory and injects a compact skill registry (names + descriptions) into the system prompt of every inference request, so the model always knows what skills exist and when to use them — at zero tool-call cost.

2. Exposes an HTTP MCP server with two tools so the model can load the full content of a skill (or any file within it) when it decides the skill is relevant.

Clients (Open WebUI, curl, any OpenAI-compatible tool) point at llama-skills instead of llama-server directly. The llama-server WebUI registers the MCP endpoint under *Manage Servers*. Everything else is unchanged.

## 4. Functional Specification

### 4.1 Project structure

Single `uv` Python project in this repo (`llama-skills`). One process hosts both the proxy and the MCP server on the same port, differentiated by path.

The Python package is **`skills_proxy`** (`skills-proxy` in prose; import path uses underscores). The repo root stays **`llama-skills`**. Modules are split by boundary (see §4.10):

```
llama-skills/
├── pyproject.toml
├── src/
│   └── skills_proxy/
│       ├── config.py         # Settings from environment variables
│       ├── models.py         # SkillEntry and domain exceptions
│       ├── skill_store.py    # SkillStore protocol + FilesystemSkillStore
│       ├── registry.py       # Pure registry formatting and message injection
│       ├── proxy.py          # HTTP proxy with skill injection
│       ├── mcp_server.py       # FastMCP Streamable HTTP tools
│       └── main.py           # Composition root, routes, lifespan, CLI entry
├── tests/
└── deploy/
    └── llama-skills.service
```

### 4.2 Port and routing

Default port: **8081** (assume llama-server is using 8080 by default)

| Path prefix | Handler |
|---|---|
| `POST /v1/chat/completions` | Skill-injecting proxy |
| `/mcp` | MCP Streamable HTTP endpoint |
| Everything else | Transparent passthrough to llama-server |

### 4.3 Skills directory

Default location: configurable via `LLAMA_SKILLS_DIR` environment variable.

Follows the Agent Skills open standard directory structure:

```
skills/
└── <skill-name>/
    ├── SKILL.md          # required: YAML frontmatter + Markdown body
    ├── scripts/          # optional
    ├── references/       # optional
    └── assets/           # optional
```

`SKILL.md` frontmatter fields read by llama-skills:

| Field | Required | Used for |
|---|---|---|
| `name` | Yes (must match folder name) | Registry entry identifier |
| `description` | Yes | Injected into system prompt |
| `when_to_use` | No | Appended to description in registry if present |
| `disable-model-invocation` | No | If `true`, skill is excluded from the registry |

All other frontmatter fields are passed through to `get_skill` as raw file content but are not parsed or acted on by llama-skills.

### 4.4 Proxy: skill injection

On every `POST /v1/chat/completions` request:

1. Scan `LLAMA_SKILLS_DIR`, parse frontmatter from each `*/SKILL.md`. Skills missing a `name` or `description`, or with `disable-model-invocation: true`, are silently skipped.
2. If no skills remain after filtering, leave the request unchanged (no registry text, no new system message).
3. Otherwise build a skills registry block (see §4.4.1) and prepend it to the existing system message, or insert one if the request has no system message.
4. Forward the (possibly modified) request to llama-server. Stream the response back to the client unchanged.

All other request fields (`model`, `temperature`, `tools`, `stream`, etc.) are forwarded unmodified.

#### 4.4.1 Registry block format

```
## Available Skills

You have access to the following skills. When the user's request matches a skill's purpose, use MCP `get_skill` with the skill name to load its full instructions before proceeding.

- **<name>**: <description> [<when_to_use>]
- **<name>**: <description>
```

The registry block is placed at the top of the system message, separated from the original content by a blank line.

### 4.5 MCP server: tools

Implements the MCP Streamable HTTP protocol (`2025-11-25` spec), JSON-RPC 2.0, following the same transport as `mcp-curl`. CORS headers required for browser-side client access.

#### Tool: `get_skill`

Retrieve a file from within a skill folder.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Skill folder name (must be a direct child of `LLAMA_SKILLS_DIR`) |
| `path` | string | No | Relative path of the file to retrieve within the skill folder. Defaults to `SKILL.md`. |

Returns the UTF-8 text content of the requested file.

Errors:
- Skill name does not exist → tool error: `"skill '<name>' not found"`
- Path resolves outside the skill folder (directory traversal attempt) → tool error: `"invalid path"`
- File does not exist → tool error: `"file not found: <path>"`

#### Tool: `list_skill_tree`

Return the file and directory structure of a skill folder.

| Parameter | Type | Required | Description |
|---|---|---|---|
| `name` | string | Yes | Skill folder name |

Returns a newline-separated list of relative paths within the skill folder, one per line, directories indicated by a trailing `/`. Example:

```
SKILL.md
references/
references/REFERENCE.md
scripts/
scripts/helper.py
```

Errors:
- Skill name does not exist → tool error: `"skill '<name>' not found"`

### 4.6 Configuration

All configuration via environment variables, set in the systemd service unit:

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SKILLS_DIR` | n/a | Skills directory path |
| `LLAMA_SKILLS_BACKEND` | `http://localhost:8080` | llama-server URL |
| `LLAMA_SKILLS_PORT` | `8081` | Port to listen on |
| `LLAMA_SKILLS_HOST` | `0.0.0.0` | Bind address |

### 4.7 Systemd service

Service file template: [deploy/llama-skills.service](deploy/llama-skills.service) (install to `/etc/systemd/system/llama-skills.service`).  
Enabled at boot, restarts on failure, independent of llama-server.

UFW: port 8081 must be open inbound (same as the llama-server port policy).

Operational install and enable steps: [INSTALL.md](INSTALL.md).

### 4.8 Client configuration

After deploying llama-skills:

- **Open WebUI:** change the backend model API URL from `http://llm-host.local:8080` to `http://llm-host.local:8081`
- **llama-server WebUI (for skill activation):** add `http://llm-host.local:8081/mcp/` under *Manage Servers*
- **Direct API clients:** replace `:8080` with `:8081` in request URLs; no other changes

Step-by-step client setup and verification: [INSTALL.md](INSTALL.md).

### 4.9 Skills directory hot reload

The skills directory is scanned on every request. No restart is required to add, edit, or remove skills. There is no caching of parsed frontmatter between requests.

### 4.10 Architecture notes

Iteration 1 implements the behaviour above with modular boundaries so iteration 2 can add caching without rewriting transports:

| Module (`src/skills_proxy/`) | Responsibility |
|---|---|
| `config.py` | Environment variables → immutable `Settings` |
| `models.py` | `SkillEntry`, domain exceptions (no I/O) |
| `skill_store.py` | All filesystem access via `SkillStore` protocol |
| `registry.py` | Pure `build_registry_block` + `inject_registry` |
| `proxy.py` | HTTP forwarding; calls registry + store |
| `mcp_server.py` | FastMCP tools; maps domain errors to tool errors |
| `main.py` | Composition root only |

`FilesystemSkillStore` rescans on every call. A future `CachedSkillStore` wrapper can implement the same `SkillStore` protocol without changing `proxy.py` or `mcp_server.py`.

FastMCP runs with `stateless_http=True`, `json_response=True`, and `streamable_http_path="/"` mounted at `/mcp` (clients use `/mcp/`).

## 5. Out of scope

- **Skill execution:** llama-skills never runs scripts or processes within a skill folder
- **Skill installation or package management:** no registry integration, no `skills install`
- **Multi-level skill directories** (project-level vs. user-level precedence): single configured directory only
- **Semantic skill matching:** the registry block is injected verbatim; skill selection is left entirely to the model
- **Authentication:** llama-skills inherits the same trust model as llama-server — LAN-only, no auth
