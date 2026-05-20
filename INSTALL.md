# Installing llama-skills

This guide covers local development setup, production deployment on your inference host, client configuration, and smoke-test verification. For a high-level overview, see [README.md](README.md). For design rationale and behaviour details, see [llama-skills.md](llama-skills.md).

## Updating
A quick note on updating an existing installation:
```bash
git pull && uv sync && sudo systemctl restart llama-skills && systemctl status llama-skills
```

## Prerequisites

- Python 3.11 or newer
- [uv](https://docs.astral.sh/uv/) for package management
- A running llama-server instance (default `http://localhost:8080`)
- A skills directory following the [Agent Skills specification](https://agentskills.io/specification)

## Local development install

1. Clone the repository and enter the project directory.

2. Install dependencies:

   ```powershell
   uv sync
   ```

   This creates a `.venv` in the project root. Use `uv run` to execute commands inside that environment.

3. Set required environment variables:

   ```powershell
   $env:LLAMA_SKILLS_DIR = "/path/to/local/skills/folder/"
   $env:LLAMA_SKILLS_BACKEND = "http://localhost:8080"   # optional
   $env:LLAMA_SKILLS_PORT = "8081"                       # optional
   $env:LLAMA_SKILLS_PUBLIC_URL = "http://llm-host.local:8081"  # optional; reverse-proxy / fixed URL
   ```

4. Start the service:

   ```powershell
   uv run llama-skills
   ```

5. Verify the process is listening on port 8081 and that `LLAMA_SKILLS_DIR` contains at least one valid skill folder with `SKILL.md`.

## Production deployment

1. Copy the project to the target host (for example `/opt/llama-skills`).

2. Run `uv sync` on the host to create the virtual environment.

3. Install the systemd unit from [deploy/llama-skills.service](deploy/llama-skills.service):

   ```bash
   sudo cp deploy/llama-skills.service /etc/systemd/system/
   sudo systemctl daemon-reload
   ```

4. Edit the unit file `Environment=` lines for your paths and backend URL, then enable and start:

   ```bash
   sudo systemctl enable --now llama-skills
   sudo systemctl status llama-skills
   ```

   Adjust `User`, `WorkingDirectory`, and `ExecStart` if your install path differs from `/opt/llama-skills`.

## Firewall

Open inbound TCP port **8081** on the host firewall. On a Linux host with UFW, for example:

```bash
sudo ufw allow 8081/tcp
```

Apply the same LAN-only trust model as llama-server port 8080.

## Client configuration

After llama-skills is running:

- **Open WebUI:** change the backend model API URL from `http://llm-host.local:8080` to `http://llm-host.local:8081`.
- **llama-server WebUI (skill activation):** use llama-skills as the API base (`http://llm-host.local:8081`), start llama-server with `--jinja`, and enable **get_skill** and **list_skill_tree** in the **Tools** selector.
- **Direct API clients:** replace `:8080` with `:8081` in request URLs. No other changes are required.

If llama-skills sits behind another reverse proxy, set `LLAMA_SKILLS_PUBLIC_URL` to the URL clients use (for example `https://llm.example.com`). The proxy injects that base URL into chat completions so the model can guide users through **Tools** setup when skill tools are missing.

## Verification

llama-skills forwards almost all HTTP traffic to llama-server. The proxy does **not** forward the client `Host` header (that breaks llama-server URL construction with `invalid URL: no scheme`); it sets `X-Forwarded-Proto` and `X-Forwarded-Host` instead.

For the llama-server WebUI **CORS proxy** (`/cors-proxy`), llama-skills answers `HEAD /cors-proxy` locally (availability probe) and adds `http://` to scheme-less `url=` query parameters before forwarding.

If llama-server is not running or `LLAMA_SKILLS_BACKEND` is wrong, passthrough routes (including `GET /`) return **502** with `llama-server unreachable`, not a browser-friendly page from llama-skills itself.

Run these checks after deployment:

1. **Passthrough:** `GET http://<host>:8081/v1/models` should return the same response as llama-server on port 8080. Confirm llama-server is up first (`curl http://127.0.0.1:8080/v1/models` on the host).

2. **Registry injection:** send a `POST /v1/chat/completions` request with a `Host` header matching your client URL and confirm the forwarded body includes `## Available Skills` and `## Tools setup (llama-server WebUI)` with your `http://<host>:8081` base URL (inspect llama-server logs or a temporary backend proxy).

3. **Skill tools:** `GET http://<host>:8081/tools` should list `get_skill` and `list_skill_tree`. `POST http://<host>:8081/tools` with body `{"tool":"get_skill","params":{"name":"<skill-folder>"}}` should return `plain_text_response` with the skill body.

4. **Hot reload:** add or edit a skill under `LLAMA_SKILLS_DIR` without restarting llama-skills; the new skill should appear in the next chat request registry.

## Running tests locally

```powershell
uv run pytest
uv run ruff check .
uv run ruff format --check .
```
