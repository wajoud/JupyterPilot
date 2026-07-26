# 🧠 JupyterPilot: AI Extension Core

This directory contains the source code for the **JupyterPilot** Python package, which implements:
- IPython magic commands (`%do` and `%fix`) for in-notebook AI assistance.
- The provider-agnostic LLM client supporting local Ollama and cloud APIs.
- **RBAC** (`admin.py`) — 2-tier role enforcement for the SSH spawner.
- **Session Store** (`session_store.py`) — SQLite-backed state for crash recovery.
- **Seed CLI** (`seed_sqlite.py`) — Bootstrap the DB from `user_mapping.json`.

---

## 🏗️ Module Architecture

```
src/jupyterpilot/          ← Installable package (pip install -e .)
├── __init__.py            ← load_ipython_extension() registration hook
├── extension.py           ← %do / %fix magic command implementations
└── provider.py            ← LLM provider bridge (Ollama + LiteLLM)

jupyterpilot/              ← Hub-side infrastructure (imported by spawner.py)
├── admin.py               ← RBACManager — 2-tier role enforcement
├── session_store.py       ← SessionStore — SQLite team mappings + session state
└── seed_sqlite.py         ← CLI: seed DB from user_mapping.json
```

---

## 📦 Module Details

### [`__init__.py`](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/__init__.py)
Exposes `load_ipython_extension(ipython)`, the registration hook IPython calls automatically when executing `%load_ext jupyterpilot`.

---

### [`extension.py`](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/extension.py)
Implements the magic commands using IPython APIs:

- **`%do <prompt>`**: Passes user instructions to the LLM and injects the resulting Python code directly into the next cell using `self.shell.set_next_input(code)`.
- **`%fix`**: Accesses the last exception details using `sys.last_type`, `sys.last_value`, and `sys.last_traceback`. Bundles the traceback and failed cell content together and queries the AI engine for a solution.
- **State/Context preservation**: Parses notebook history via `self.shell.history_manager.input_hist_raw`, filters empty lines and magic invocations, and merges the last 3 cells into a single context string.

---

### [`provider.py`](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/provider.py)
Routes requests to the AI engine:

- **Config Loader**: Resolves configuration hierarchically:
  1. User settings: `~/.jupyterpilot/config.json`
  2. System settings: `/etc/jupyterpilot/config.json`
  3. Built-in defaults: Local Ollama on port `11434` with model `qwen2.5-coder:7b`
- **Local Mode**: Sends JSON payloads directly to an Ollama server.
- **Cloud Mode**: Dynamically configures credentials and forwards tasks via `litellm` (OpenAI, Anthropic, Gemini, etc.).
- **Code Cleaning**: Strips surrounding markdown blocks (` ```python `, ` ``` `) from AI output, leaving only executable code.

---

### [`admin.py`](file:///Users/wajoud/projects/Github/JupyterPilot/jupyterpilot/admin.py)
Lightweight RBAC manager for the SSH spawner. **No JupyterHub import** — fully unit-testable.

**2-tier model:**

| Role | How determined | Rights |
|---|---|---|
| `admin` | `user.admin == True` (set via JupyterHub Admin Panel or `admin_users` in `hub_settings.json`) | Stop/inspect any user's remote session |
| `user` | Everyone else | Manage only their own session |

**Key methods:**
```python
rbac = RBACManager()
rbac.is_admin(user)                        # bool
rbac.get_role(user)                        # "admin" | "user"
rbac.assert_can_act_on(actor, "username")  # raises PermissionError if denied
```

To promote a user to admin: **JupyterHub Admin Panel → Users → ☑ Make Admin**. No code or DB changes required.

---

### [`session_store.py`](file:///Users/wajoud/projects/Github/JupyterPilot/jupyterpilot/session_store.py)
Zero-dependency SQLite wrapper (`sqlite3` — Python stdlib) providing:

**Two tables:**

| Table | Purpose |
|---|---|
| `team_mappings` | Team → VM routing (replaces `user_mapping.json` as the live source) |
| `user_sessions` | Per-user session state — survives hub crashes for crash-safe `poll()` and `stop()` |

**Key API:**
```python
store = SessionStore("/var/lib/jupyterhub/jupyterpilot_state.db")
store.init_db()                              # create tables (idempotent)
store.ping()                                 # health check → bool
store.get_mapping("team_alpha")              # → dict | None
store.set_mapping("team_alpha", ip, key)
store.get_session("alice")                   # → dict | None
store.set_session("alice", status="running", port=8888, ...)  # upsert
store.clear_session("alice")                 # delete row
```

**Thread safety**: Module-level `threading.Lock` on all writes — safe under JupyterHub's asyncio + thread-pool model.

**Graceful fallback**: If `ping()` returns `False`, the spawner automatically falls back to reading `user_mapping.json` without crashing.

---

### [`seed_sqlite.py`](file:///Users/wajoud/projects/Github/JupyterPilot/jupyterpilot/seed_sqlite.py)
One-shot CLI to bootstrap the `team_mappings` table from `user_mapping.json`. Run once on first deploy or after a DB file loss:

```bash
python -m jupyterpilot.seed_sqlite \
    --db      /var/lib/jupyterhub/jupyterpilot_state.db \
    --mapping user_mapping.json
```

Output:
```
  ✓ team_alpha                     → 10.0.1.15
  ✓ team_beta                      → 10.0.1.16

[DONE] Seeded 2 team(s), skipped 0.
       DB: /var/lib/jupyterhub/jupyterpilot_state.db
```

The script is **idempotent** — running it again on the same mapping safely overwrites existing rows.

---

## 🚀 Loading the AI Extension

### Manual Loading (in a running Jupyter session)
```python
# Install the package first
# pip install -e .

%load_ext jupyterpilot
```

### Automatic System Startup
Copy the standalone extension script to the IPython startup folder so it loads automatically in every session:
```bash
mkdir -p ~/.ipython/profile_default/startup/
cp jupyterpilot_extension.py ~/.ipython/profile_default/startup/
```
*(No need to run `%load_ext` when loaded as a startup script.)*
