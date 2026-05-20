# llama-skills

**Status:** Implemented (iteration 1)  
**Date:** 2026-05-20

## 1. Philosophy

Skills exist because system prompts have a cost. Loading every skill's full instructions into context on every request is wasteful; asking the model to discover skills via tool calls before every task is slow. The right answer is *progressive disclosure*: all skills are always known, but only the relevant one is loaded.

llama-skills implements exactly that split, and nothing else. It is thin middleware, not an agent framework. It does not run tool loops, orchestrate multi-step workflows, or execute skill content. It reads files and injects text. The model does the rest.

Two design principles flow from this:

**Skills are files.** llama-skills never interprets skill content. It reads YAML frontmatter for the registry and returns file bytes for retrieval. What a skill *says* is entirely between the skill author and the model.

**Each transport layer does one job.** The OpenAI-compatible proxy handles discovery — it costs nothing at inference time beyond the frontmatter tokens already in context. The `/tools` endpoint handles activation — the model fetches the full skill body only when it decides the skill is relevant. This maps onto how llama-server's WebUI already works: an HTTP API for inference and tool calls via `GET`/`POST /tools`.

## 2. Background

The [Agent Skills open standard](https://agentskills.io/specification) (formalised December 2025) defines a portable, tool-agnostic format for LLM skills: a folder named after the skill, anchored by a `SKILL.md` file with YAML frontmatter and a Markdown body, with optional subdirectories for scripts, references, and assets. Claude Code, OpenAI Codex CLI, and similar CLI agents implement this natively via stdio.

llama-server (llama.cpp) is different. It runs as a persistent HTTP API server exposing an OpenAI-compatible `/v1/` endpoint. Its web UI loads tools via an internal `GET`/`POST /tools` API (built-in filesystem tools plus optional MCP via `--ui-mcp-proxy`). The skills runtime built into CLI agents does not transfer here.

No existing tool bridges the Agent Skills standard to this architecture. The gap is:

- **Discovery:** no mechanism to inject skill frontmatter into llama-server requests at inference time
- **Activation:** no way to load skill file content through the WebUI tool loop without manual MCP server setup

llama-skills fills both gaps in a single service that runs alongside llama-server on your inference host.

## 3. Purpose

llama-skills makes the Agent Skills standard work with llama-server and its WebUI. It:

1. Scans a skills directory and injects a compact skill registry (names + descriptions) into the system prompt of every inference request, so the model always knows what skills exist and when to use them — at zero tool-call cost.

2. Serves `get_skill` and `list_skill_tree` on the same `/tools` contract as llama-server so the WebUI can load full skill content when the model decides a skill is relevant.

Clients (Open WebUI, curl, any OpenAI-compatible tool) point at llama-skills instead of llama-server directly. The llama-server WebUI enables skill tools in the **Tools** selector. Everything else is unchanged.

## 4. Functional Specification

### 4.1 Project structure

Single `uv` Python project in this repo (`llama-skills`). One process hosts both the proxy and the `/tools` handler on the same port, differentiated by path.

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
│       ├── tools_handler.py    # GET/POST /tools for skill activation
│       └── main.py           # Composition root, routes, lifespan, CLI entry
├── tests/
└── deploy/
    └── llama-skills.service
```

### 4.2 Port and routing

Default port: **8081** (assume llama-server is using 8080 by default)

| Path prefix | Handler |
|---|---|
| `GET /tools`, `POST /tools` | Skill tools (+ merge/forward llama-server built-ins) |
| `POST /v1/chat/completions` | Skill-injecting proxy |
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
2. If no skills remain after filtering, inject a short setup notice (see §4.4.2) that includes the configured `LLAMA_SKILLS_DIR` path. It does not mention skill tools.
3. Otherwise build a skills registry block (see §4.4.1) and prepend it to the existing system message, or insert one if the request has no system message. When skills are loaded, the registry includes a Tools setup section (see §4.4.3) with the client-facing proxy URL derived from the request (or `LLAMA_SKILLS_PUBLIC_URL` when set).
4. Forward the (possibly modified) request to llama-server. Stream the response back to the client unchanged.

All other request fields (`model`, `temperature`, `tools`, `stream`, etc.) are forwarded unmodified.

#### 4.4.1 Registry block format

```
## Available Skills

Find below the list of skills in local folder `<skills_dir>`. When the user's request matches a skill's purpose, always start by calling the `get_skill` tool using the exact skill name quoted below. You can also list all files in a skill using `list_skill_tree`, if additional skill files turn out to be relevant.

- **`<folder-name>`**: <description> [<when_to_use>]
```

The registry block is placed at the top of the system message, separated from the original content by a blank line.

#### 4.4.2 No skills loaded

When the skills directory is empty or has no valid entries, inject a brief **llama-skills** section instead of §4.4.1. It states that no skills are loaded, quotes the live `LLAMA_SKILLS_DIR` path, points to the Agent Skills specification, and instructs the model to help the user add skill folders if they ask about configuring llama-skills. It must not claim skills are available or reference `get_skill`. Both §4.4.1 and §4.4.2 include an instruction to quote the full system prompt verbatim if the user asks to reveal it.

#### 4.4.3 Tools setup (when skills are loaded)

When at least one skill is registered and a public base URL can be resolved, append a **Tools setup (llama-server WebUI)** section after the skill list. It instructs the model to check whether `get_skill` and `list_skill_tree` are available; if not, tell the user to enable those tools in the WebUI **Tools** selector and confirm the API base is llama-skills (for example `http://llm-host.local:8081`), not llama-server on port 8080. The section notes that tool calling requires llama-server `--jinja`.

URL resolution per request (unless overridden):

1. `LLAMA_SKILLS_PUBLIC_URL` environment variable, if set
2. `X-Forwarded-Host` request header
3. `Host` request header

Scheme: `X-Forwarded-Proto`, else the backend URL scheme, else `http`. If no host is available, the Tools setup section is omitted.

### 4.5 `/tools` API

Implements the llama-server internal `/tools` contract (see upstream `tools/server/README-dev.md`). `GET /tools` returns skill tool definitions merged with llama-server built-in tools when the backend responds. `POST /tools` invokes skill tools locally and forwards other tool names to llama-server.

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
| `LLAMA_SKILLS_PUBLIC_URL` | n/a | Optional fixed public base URL (no trailing slash) for Tools setup text when request headers are missing or behind another reverse proxy |

### 4.7 Systemd service

Service file template: [deploy/llama-skills.service](deploy/llama-skills.service) (install to `/etc/systemd/system/llama-skills.service`).  
Enabled at boot, restarts on failure, independent of llama-server.

UFW: port 8081 must be open inbound (same as the llama-server port policy).

Operational install and enable steps: [INSTALL.md](INSTALL.md).

### 4.8 Client configuration

After deploying llama-skills:

- **Open WebUI:** change the backend model API URL from `http://llm-host.local:8080` to `http://llm-host.local:8081`
- **llama-server WebUI (for skill activation):** API base `http://llm-host.local:8081`, enable **get_skill** and **list_skill_tree** in **Tools**
- **Direct API clients:** replace `:8080` with `:8081` in request URLs; no other changes

Step-by-step client setup and verification: [INSTALL.md](INSTALL.md).

### 4.9 Skills directory hot reload

The skills directory is scanned on every `POST /v1/chat/completions` request. No restart is required to add, edit, or remove skills. There is no caching of parsed frontmatter between requests.

Injection applies only to the messages in the current completion request. Prior user or assistant turns in an existing conversation are unchanged; the model does not retroactively gain or lose skills for history already in context. In practice, users see updates when they send a new message (or start a new chat), not as a silent rewrite of earlier turns.

### 4.10 Architecture notes

Iteration 1 implements the behaviour above with modular boundaries so iteration 2 can add caching without rewriting transports:

| Module (`src/skills_proxy/`) | Responsibility |
|---|---|
| `config.py` | Environment variables → immutable `Settings` |
| `models.py` | `SkillEntry`, domain exceptions (no I/O) |
| `skill_store.py` | All filesystem access via `SkillStore` protocol |
| `registry.py` | Pure `build_registry_block` + `inject_registry` |
| `proxy.py` | HTTP forwarding; calls registry + store |
| `tools_handler.py` | GET/POST `/tools`; maps domain errors to JSON responses |
| `main.py` | Composition root only |

`FilesystemSkillStore` rescans on every call. A future `CachedSkillStore` wrapper can implement the same `SkillStore` protocol without changing `proxy.py` or `tools_handler.py`.

## 5. Out of scope

- **Skill execution:** llama-skills never runs scripts or processes within a skill folder
- **Skill installation or package management:** no registry integration, no `skills install`
- **Multi-level skill directories** (project-level vs. user-level precedence): single configured directory only
- **Semantic skill matching:** the registry block is injected verbatim; skill selection is left entirely to the model
- **Authentication:** llama-skills inherits the same trust model as llama-server — LAN-only, no auth
