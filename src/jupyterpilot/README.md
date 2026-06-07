# 🧠 JupyterPilot: AI Extension Core

This directory contains the source code for the **JupyterPilot** Python package, which implements the IPython magic commands (`%do` and `%fix`) and the provider-agnostic LLM client.

---

## 🏗️ Module Architecture

The package is split into three main modules:

### 1. [__init__.py](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/__init__.py)
Exposes `load_ipython_extension(ipython)`, which registration hook IPython automatically calls when executing `%load_ext jupyterpilot`.

### 2. [extension.py](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/extension.py)
Implements the magic commands using IPython APIs:
- **`%do <prompt>`**: Passes user instructions to the LLM and injects the resulting python code directly into the next cell using `self.shell.set_next_input(code)`.
- **`%fix`**: Accesses the last exception details using `sys.last_type`, `sys.last_value`, and `sys.last_traceback`. It bundles the tracebacks and the failed cell content together and queries the AI engine for a solution.
- **State/Context preservation**: Automatically parses notebook history via `self.shell.history_manager.input_hist_raw`, filters out empty lines and magic invocations, and merges the last 3 cells into a single context string.

### 3. [provider.py](file:///Users/wajoud/projects/Github/JupyterPilot/src/jupyterpilot/provider.py)
Routes requests to the AI engine:
- **Config Loader**: Resolves configurations hierarchically:
  1. User directory settings: `~/.jupyterpilot/config.json`
  2. Global system settings: `/etc/jupyterpilot/config.json`
  3. Built-in defaults: Local Ollama on port `11434` with model `qwen2.5-coder:7b`.
- **Local Mode**: Sends standard JSON payloads directly to an Ollama server.
- **Cloud Mode**: Dynamically configures credentials and forwards tasks via `litellm` (supporting OpenAI, Anthropic, Gemini, etc.).
- **Code Cleaning**: Uses robust parsing to strip away surrounding markdown blocks (e.g., ` ```python ` and ` ``` `) from AI outputs, leaving only executable code.

---

## 🚀 Loading the Extension

You can load this extension in any running IPython or Jupyter session:

### 1. Manual Loading
```python
# Install the package first
# pip install -e .

# Load the extension
%load_ext jupyterpilot
```

### 2. Automatic System Startup
To have the extension load automatically in every session, copy the standalone script to your IPython startup folder:
```bash
mkdir -p ~/.ipython/profile_default/startup/
cp jupyterpilot_extension.py ~/.ipython/profile_default/startup/
```
*(No need to execute `%load_ext` when loaded as a startup script).*
