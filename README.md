# llama-skills

Thin middleware that brings the [Agent Skills](https://agentskills.io/specification) standard to [llama-server](https://github.com/ggml-org/llama.cpp). Clients talk to llama-skills on port **8081** instead of llama-server on **8080**. The service injects a compact skill registry into every chat completion request and exposes skill activation via llama-server's `/tools` API so the WebUI can load full skill content when needed.

## Quick start

```powershell
uv sync
$env:LLAMA_SKILLS_DIR = "/path/to/local/skills/folder/"
uv run llama-skills
```

Point your OpenAI-compatible client at `http://localhost:8081`. In the llama-server WebUI, enable **get_skill** and **list_skill_tree** in the **Tools** selector (requires llama-server `--jinja`).

For production deployment, firewall rules, and client setup, see [INSTALL.md](INSTALL.md).

## Configuration

| Variable | Default | Description |
|---|---|---|
| `LLAMA_SKILLS_DIR` | *(required)* | Path to the skills directory |
| `LLAMA_SKILLS_BACKEND` | `http://localhost:8080` | llama-server base URL |
| `LLAMA_SKILLS_HOST` | `0.0.0.0` | Bind address |
| `LLAMA_SKILLS_PORT` | `8081` | Listen port |

## Skills directory

Each skill is a folder with a required `SKILL.md` (YAML frontmatter + Markdown body). Optional subdirectories include `scripts/`, `references/`, and `assets/`. See the [Agent Skills specification](https://agentskills.io/specification) for the full format.

## Development

Application code lives in `src/skills_proxy/` (import name `skills_proxy`; the CLI remains `llama-skills`).

```powershell
uv run pytest
uv run ruff check .
uv run ruff format .
```

## Further reading

- [INSTALL.md](INSTALL.md) — installation, systemd deployment, client configuration, verification
- [llama-skills.md](llama-skills.md) — design spec and architecture notes
