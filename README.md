<div align="center">

# 🚀 JupyterPilot

**Enterprise-grade AI coding partner & secure notebook isolation for JupyterHub**

[![Python](https://img.shields.io/badge/Python-3.8%2B-3776ab?style=flat-square&logo=python&logoColor=white)](https://www.python.org/)
[![JupyterHub](https://img.shields.io/badge/JupyterHub-Compatible-f37726?style=flat-square&logo=jupyter&logoColor=white)](https://jupyterhub.readthedocs.io/)
[![License: MIT](https://img.shields.io/badge/License-MIT-22c55e?style=flat-square)](LICENSE)
[![Tests](https://img.shields.io/badge/Tests-54%20passing-22c55e?style=flat-square)](tests/)
[![pip install](https://img.shields.io/badge/pip%20install-jupyterpilot-3b82f6?style=flat-square)](pyproject.toml)

</div>

---

**JupyterPilot** is a secure, high-performance AI coding partner and isolation spawner for enterprise-grade JupyterHub deployments. It decouples the hub controller from notebook execution via an SSH-based "teleport" spawner with SQLite-backed crash recovery, enforces 2-tier RBAC through the JupyterHub admin panel, and provides in-notebook AI assistance through `%do` and `%fix` magic commands.

---

## ✨ Features

| Feature | Description |
|---|---|
| 🔁 **SSH Teleport Spawner** | Launches `jupyterhub-singleuser` on isolated remote VMs per team |
| 🗄️ **SQLite Session State** | Crash-safe session recovery — `stop()` and `poll()` read from DB, not memory |
| 🔐 **2-Tier RBAC** | Admin/user roles managed entirely via JupyterHub Admin Panel |
| 🧱 **cgroups v2 Isolation** | `systemd-run --user --scope` wraps every spawn with hard `MemoryMax` + `CPUQuota` caps |
| 🔑 **Vault Secret Injection** | HashiCorp Vault KV-v2 secrets injected at spawn with zero disk I/O — opt-in, graceful degradation |
| 📊 **Live Monitoring Dashboard** | psutil agent streams CPU, RAM, disk & network I/O over WebSocket to a dark-mode real-time dashboard |
| 🏗️ **Controlled Env Strategy** | User-venv isolation at `~/.jupyterpilot/venv` keeps AI deps off the system Python |
| 🤖 **`%do` Magic** | Natural language → executable Python injected into the next cell (`--run` to execute immediately) |
| 🩹 **`%fix` Magic** | Auto-heals tracebacks — strips Jupyter internals before sending to LLM |
| 🔍 **`%review` Magic** | AST-aware code quality reviewer — static analysis + LLM prose review |
| ♻️ **`%rework` Magic** | LLM-powered refactoring with `--diff` mode to preview changes before applying |
| 🌐 **Provider Agnostic** | Local Ollama, cloud APIs (GPT-4, Claude, Gemini) or MCP tool servers |
| 🛡️ **OOM Protection** | Writes OOM score adjustments on remote VMs at spawn time |
| 🔄 **JSON Fallback** | Falls back to `user_mapping.json` if SQLite DB is unreachable |

---

## 🗺️ Architecture

JupyterPilot operates across two layers: **Infrastructure Isolation** and **Notebook AI Assistance**.

### Spawning & Session State Flow

```mermaid
graph TD
    User([User]) -->|Google OAuth| Hub[JupyterHub Server]
    Hub -->|CustomSpawner + RBAC| SSH[Paramiko SSH Connection]
    SSH -->|SQLite session lookup| Store[(jupyterpilot_state.db)]
    SSH -->|Query Remote Port| PortScript[Run get_port.py]
    PortScript -->|Return Port| PortCheck[Check Port availability]
    PortCheck -->|If Busy| Kill[Kill stale port processes via fuser]
    Kill -->|Setup OOM| OOM[Write OOM script to profile startup]
    OOM -->|Launch| SingleUser[Launch jupyterhub-singleuser]
    SingleUser -->|Proxy Traffic| Proxy[HTTP Proxy]
    Proxy --> User
    SingleUser -->|Write session state| Store
```

### In-Notebook AI Loop (`%do` / `%fix`)

```mermaid
graph LR
    Input[Prompt or Python Error] -->|Collect context| Extension[IPython Extension]
    Extension -->|Last 3 Cells + Error Traceback| Provider[LLM Provider]
    Provider -->|Local Mode| Ollama[Ollama / Qwen2.5-Coder]
    Provider -->|Cloud Mode| LiteLLM[GPT-4 / Claude / Gemini]
    Ollama -->|Cleaned Python Code| Next[Inject into next Notebook Cell]
    LiteLLM -->|Cleaned Python Code| Next
```

---

## 📦 Repository Structure

```
JupyterPilot/
├── spawner.py                      # Custom SSH spawner — RBAC, cgroups, Vault, SQLite lifecycle
├── jupyterhub_config.py            # JupyterHub daemon config (loaded at hub start)
├── jupyterpilot_extension.py       # Standalone IPython extension (%do / %fix)
├── hub_settings.json               # Network, auth, resource limits & Vault config
├── user_mapping.json               # VM routing fallback / seed source
│
├── jupyterpilot/                   # Hub-side core package
│   ├── admin.py                    #   RBACManager — 2-tier role enforcement
│   ├── session_store.py            #   SQLite session + team mapping store
│   ├── seed_sqlite.py              #   CLI: bootstrap SQLite DB from JSON
│   ├── vault_client.py             #   HashiCorp Vault KV-v2 client (raw requests)
│   ├── metrics_agent.py            #   psutil metrics agent — runs on Worker VMs
│   ├── monitoring_handler.py       #   Tornado WS + HTTP handlers for live dashboard
│   └── static/
│       └── monitoring.html         #   Dark-mode real-time monitoring dashboard
│
├── src/jupyterpilot/               # Installable AI extension package
│   ├── extension.py                #   %do / %fix magic command implementations
│   └── provider.py                 #   LLM provider bridge (Ollama + LiteLLM)
│
├── AWS_EC2_DEPLOYMENT.md           # End-to-end AWS EC2 deployment guide
└── tests/                          # 54-test mock-based unit suite
    ├── conftest.py                 #   Module mock bootstrap
    ├── test_spawner.py             #   SSH lifecycle tests
    ├── test_config.py              #   Hub config & security handler tests
    └── test_spawner_lifecycle.py   #   RBAC, SessionStore & crash recovery tests
```

---

## 🛠️ Installation

### Prerequisites
- Python 3.8+
- Target VMs: `netstat`, `fuser` installed
- Hub machine: writable path for SQLite DB

### 1. Install the package

```bash
git clone https://github.com/wajoud/JupyterPilot.git /opt/jupyterpilot
cd /opt/jupyterpilot
pip install -e .
```

### 2. Configure hub settings

Edit `hub_settings.json`:
```json
{
  "hub_ip":       "10.0.0.10",
  "proxy_api_url":"http://10.0.0.10:5432",
  "hub_api_url":  "http://10.0.0.10:8081/hub/api",
  "hub_bind_url": "http://10.0.0.10:8081",
  "hub_port":     8000,
  "hosted_domain":"your-company.com",
  "admin_users":  ["admin@your-company.com"],
  "mapping_file": "user_mapping.json",
  "db_path":      "/var/lib/jupyterhub/jupyterpilot_state.db",

  "resource_limits": {
    "memory_max": "512M",
    "cpu_quota":  "50%"
  },

  "vault_enabled":     false,
  "vault_secret_path": "secret/jupyterpilot"
}
```

Add your team → VM mappings to `user_mapping.json`:
```json
{
  "team_alpha": {
    "server_ip":      "10.0.1.15",
    "server_ssh_key": "/etc/jupyterhub/keys/team_alpha.pem"
  }
}
```

### 3. Bootstrap the SQLite database (run once on deploy)

```bash
python -m jupyterpilot.seed_sqlite \
    --db      /var/lib/jupyterhub/jupyterpilot_state.db \
    --mapping user_mapping.json
```

### 4. Load the AI extension (optional, on worker VMs or user machines)

```bash
# Auto-load in every IPython/Jupyter session
mkdir -p ~/.ipython/profile_default/startup/
cp jupyterpilot_extension.py ~/.ipython/profile_default/startup/
```

Or configure your AI backend at `~/.jupyterpilot/config.json`:
```json
{
  "mode": "cloud",
  "cloud": {
    "provider": "openai",
    "model":    "gpt-4o",
    "api_key":  "sk-..."
  }
}
```

### 5. Enable HashiCorp Vault secrets (optional)

Set environment variables on the Hub VM before starting JupyterHub:
```bash
export VAULT_ADDR=http://127.0.0.1:8200
export VAULT_TOKEN=your-root-or-policy-token
```
Then in `hub_settings.json` set `"vault_enabled": true`. Secrets stored at `secret/jupyterpilot/<username>` are automatically injected as kernel environment variables at spawn time with zero disk I/O.

### 6. Enable cgroups v2 Resource Limits (optional)

If you specified `memory_max` or `cpu_quota` in `hub_settings.json`, the Spawner will automatically wrap the remote server in `systemd-run --user`. 
**CRITICAL:** You must enable lingering for the target user on the Worker VM, otherwise Ubuntu's `systemd-logind` will kill the server exactly 7 seconds after it spawns:

```bash
# Run this on the Worker VM
sudo loginctl enable-linger <username>
```

### 7. Start the monitoring agent on Worker VMs (optional)

The background metrics agent is required to stream live hardware data to the Hub's monitoring dashboard.
On your Worker VM:
```bash
sudo git clone https://github.com/wajoud/JupyterPilot.git /opt/jupyterpilot
sudo pip3 install psutil websockets --break-system-packages

python3 /opt/jupyterpilot/jupyterpilot/metrics_agent.py \
    --hub ws://<HUB_PRIVATE_IP>:8000/monitoring/ws \
    --interval 2
```
Then visit `http://<HUB_PUBLIC_IP>:8000/monitoring` to see the live dashboard!

---

## 🤖 Magic Commands Reference

Load the extension in any Jupyter session:
```python
%load_ext jupyterpilot.extension
```

| Command | Description |
|---|---|
| `%do <prompt>` | Generate Python code from a natural language prompt |
| `%do --run <prompt>` | Generate **and immediately execute** the code |
| `%fix` | Auto-heal the last exception (strips Jupyter internal frames before sending to LLM) |
| `%review` | AST static analysis + LLM prose review of the last cell |
| `%review -n 3` | Review the last 3 cells |
| `%review --all` | Review the entire notebook session |
| `%rework <instruction>` | Refactor the last cell per your instruction |
| `%rework --diff <instruction>` | Preview the proposed changes as a unified diff before applying |

### Config (`~/.jupyterpilot/config.json`)

```json
{
  "mode": "local",
  "local":  { "url": "http://localhost:11434/api/generate", "model": "qwen2.5-coder:7b" },
  "cloud":  { "provider": "openai", "model": "gpt-4o-mini", "api_key": "sk-..." },
  "mcp":    { "server_url": "http://localhost:3000", "tools": ["generate_code"] },
  "rate_limit": { "requests_per_minute": 20 }
}
```

---

## 🔐 Security Model

| Control | Implementation |
|---|---|
| **OAuth Domain Lock** | `hosted_domain` in `hub_settings.json` restricts login to one Google Workspace |
| **Admin Isolation** | `admin_access = False` — admins cannot enter user containers directly |
| **2-Tier RBAC** | `user.admin` from JupyterHub panel; no code changes needed to promote users |
| **Cross-User Blocking** | `BlockOtherUsersHandler` returns `403` on `/user/<other>/` path access |
| **OOM Enforcement** | `oom_score_adj = 500` on remote VMs prevents kernel runaway from crashing system daemons |

---

## 🧪 Running Tests

All 54 tests run without any real SSH, JupyterHub, or database infrastructure:

```bash
# Install dev dependencies
pip install -e ".[dev]"

# Run the full suite
pytest -v tests/

# Individual suites
pytest -v tests/test_spawner_lifecycle.py   # RBAC + SQLite + crash recovery (38 tests)
pytest -v tests/test_spawner.py             # SSH spawner lifecycle (11 tests)
pytest -v tests/test_config.py             # Hub config & security (5 tests)
```

---

## 🗺️ Roadmap

| Task | Status | Description |
|---|---|---|
| **Task 1** — Admin Core & Lifecycle | ✅ Done | SQLite session state, 2-tier RBAC, `start/stop/poll/clear_state` |
| **Task 2** — cgroups v2 Isolation | ✅ Done | `systemd-run` hard `MemoryMax` + `CPUQuota` caps via `pre_spawn_hook` |
| **Task 3** — Vault Secret Injection | ✅ Done | Raw-requests Vault KV-v2 client; zero-disk env injection at spawn |
| **Task 4** — Live Monitoring Dashboard | ✅ Done | psutil agent → WebSocket → dark-mode real-time dashboard for all users |
| **Task 5** — Controlled Env Strategy | ✅ Done | User venv at `~/.jupyterpilot/venv`; `[ai]` optional package extra |
| **Task 6** — LLM & MCP Connectivity | ✅ Done | 3 backends (Ollama, LiteLLM, MCP) with retry, rate-limiting & Vault key reads |
| **Task 7** — Core Magics Refinement | ✅ Done | Cell output context, traceback stripping, `--run` flag, IPython store integration |
| **Task 8** — New Agentic Magics | ✅ Done | `%review` (AST + LLM) and `%rework --diff` (unified diff preview before apply) |

---

## 🤝 Contributing

Contributions are welcome! Please follow these steps:

1. **Fork** the repository
2. **Create a branch**: `git checkout -b feat/your-feature`
3. **Make changes** and ensure tests pass: `pytest -v tests/`
4. **Open a Pull Request** — a code review from [@wajoud](https://github.com/wajoud) will be automatically requested via CODEOWNERS

### Development Setup

```bash
git clone https://github.com/wajoud/JupyterPilot.git
cd JupyterPilot
pip install -e ".[dev]"
pytest -v tests/   # all 54 should pass
```

---

## 📄 License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

Built with 🔧 by [@wajoud](https://github.com/wajoud) · Star ⭐ if this helps your team!

</div>
