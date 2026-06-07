# 🧪 JupyterPilot: Testing Subsystem

This directory contains the unit tests for the JupyterHub integrations of JupyterPilot, including the remote SSH spawner and security handlers.

---

## 🏗️ Mocking Architecture

Since JupyterHub and its dependencies (`paramiko`, Google OAuthenticator, etc.) are complex and often require real infrastructure (running VM instances, oauth credential setups, etc.) to load, we use a fully mocked runtime namespace:

1. **Imports Mocking (`conftest.py`)**:
   - Intercepts and patches `sys.modules` for missing external dependencies like `jupyterhub.spawner`, `jupyterhub.handlers`, `oauthenticator.google`, and `paramiko`.
   - Stubs the base spawner class `MockSpawner` and handler class `MockBaseHandler` so Python can subclass them during test collection without raising `ModuleNotFoundError`.
2. **Global Config Stub (`get_config`)**:
   - Injects a fake global `get_config()` function returning a nested `MagicMock` into the Python `builtins` namespace, enabling safe evaluation of `jupyterhub_config.py`.

---

## 📁 Directory Structure

- **[conftest.py](file:///Users/wajoud/projects/Github/JupyterPilot/tests/conftest.py)**: Test suite bootstrap configuration, mocking external integrations.
- **[test_spawner.py](file:///Users/wajoud/projects/Github/JupyterPilot/tests/test_spawner.py)**: Tests for [spawner.py](file:///Users/wajoud/projects/Github/JupyterPilot/spawner.py). Covers:
  - Dynamic user mapping resolution and validation errors.
  - SSH port allocation and stale process termination logic (`netstat` / `fuser`).
  - Safe spawning inside remote VMs and graceful stops.
  - Asynchronous status polling.
- **[test_config.py](file:///Users/wajoud/projects/Github/JupyterPilot/tests/test_config.py)**: Tests for [jupyterhub_config.py](file:///Users/wajoud/projects/Github/JupyterPilot/jupyterhub_config.py). Covers:
  - Parsing settings from mock configurations.
  - The `BlockOtherUsersHandler` request validator to confirm it redirects unauthorized users and blocks requests for other user server roots with `403 Forbidden`.

---

## 🚀 How to Run the Tests

The test suite uses **pytest** and **anyio** (pre-installed in Python Anaconda/Base envs) to run asynchronous tests.

Run the following command from the root directory:
```bash
pytest -v tests/
```
