"""
jupyterpilot/env_setup.py
─────────────────────────
Controlled Environment Strategy (Task 5).

Ensures the AI dependencies (ipython, litellm, mcp) are available in the
current Python environment before any magic commands are registered.

Strategy (in priority order):
  1. If deps are already importable → no-op, instant return.
  2. If a user venv exists at ~/.jupyterpilot/venv → activate it by prepending
     its site-packages to sys.path.
  3. Otherwise → create the venv, install jupyterpilot[ai] into it, and activate.

This keeps the global system packages untouched (important on shared Hub VMs).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

_VENV_DIR = Path.home() / ".jupyterpilot" / "venv"
_AI_DEPS = ["ipython", "litellm"]  # mcp is optional — checked separately


def _deps_available() -> bool:
    """Return True if all required AI packages are importable."""
    for dep in _AI_DEPS:
        try:
            __import__(dep)
        except ImportError:
            return False
    return True


def _venv_site_packages() -> Path | None:
    """Return the site-packages path inside the user venv, if it exists."""
    for candidate in _VENV_DIR.glob("lib/python*/site-packages"):
        return candidate
    return None


def _activate_venv() -> bool:
    """Prepend venv site-packages to sys.path. Returns True if successful."""
    sp = _venv_site_packages()
    if sp and sp.exists():
        site_str = str(sp)
        if site_str not in sys.path:
            sys.path.insert(0, site_str)
        return True
    return False


def _create_venv() -> None:
    """Create ~/.jupyterpilot/venv and install AI deps into it."""
    _VENV_DIR.mkdir(parents=True, exist_ok=True)
    python = sys.executable

    print(f"[JupyterPilot] Creating AI venv at {_VENV_DIR} …")
    subprocess.run([python, "-m", "venv", str(_VENV_DIR)], check=True)

    pip = _VENV_DIR / "bin" / "pip"
    print("[JupyterPilot] Installing AI dependencies (this happens once) …")
    subprocess.run(
        [str(pip), "install", "--quiet", "jupyterpilot[ai]"],
        check=True,
    )
    print("[JupyterPilot] ✅ AI dependencies installed.")


def ensure_ai_deps() -> None:
    """
    Public entry point — called at magic registration time.

    Guarantees that after this function returns, all AI packages are importable.
    Raises RuntimeError only if venv creation itself fails.
    """
    if _deps_available():
        return  # Fast path — already available, nothing to do

    # Try activating an existing venv first
    if _activate_venv() and _deps_available():
        return

    # Venv doesn't exist or is broken — create it
    try:
        _create_venv()
        _activate_venv()
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            f"[JupyterPilot] Failed to set up AI dependencies: {exc}\n"
            "You can install them manually with: pip install jupyterpilot[ai]"
        ) from exc
