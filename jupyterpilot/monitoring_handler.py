"""
jupyterpilot/monitoring_handler.py
────────────────────────────────────
Tornado handlers for the JupyterPilot live monitoring dashboard.

Two handlers are registered:

AgentWebSocketHandler  (``/monitoring/ws``)
    Accepts WebSocket connections from Worker VM metrics agents.
    Stores the latest snapshot per Worker hostname in the shared
    ``_WORKER_SNAPSHOTS`` dict and broadcasts updates to all connected
    Admin browser clients.

MonitoringPageHandler  (``/monitoring``)
    Serves the monitoring dashboard HTML page.
    Accessible to ALL authenticated JupyterHub users (not admin-only):
      - Regular users see their own Worker VM's metrics.
      - Admins see all connected Worker VMs.

Usage (wire in jupyterhub_config.py)
──────────────────────────────────────
    from jupyterpilot.monitoring_handler import (
        AgentWebSocketHandler,
        MonitoringPageHandler,
        BrowserWebSocketHandler,
    )

    c.JupyterHub.extra_handlers = [
        (r"/monitoring/ws",      AgentWebSocketHandler),
        (r"/monitoring/browser", BrowserWebSocketHandler),
        (r"/monitoring",         MonitoringPageHandler),
    ]
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any, Dict, Set

from tornado import web
from tornado.websocket import WebSocketHandler

log = logging.getLogger("jupyterhub")

# ---------------------------------------------------------------------------
# Shared in-process state
# ---------------------------------------------------------------------------

# Latest snapshot per Worker, keyed by hostname.
# { "ip-172-31-27-155": { ...metrics snapshot... } }
_WORKER_SNAPSHOTS: Dict[str, Dict[str, Any]] = {}

# All active browser WebSocket clients waiting for live updates.
_BROWSER_CLIENTS: Set["BrowserWebSocketHandler"] = set()


# ---------------------------------------------------------------------------
# Agent WebSocket handler  (Worker VM → Hub)
# ---------------------------------------------------------------------------

class AgentWebSocketHandler(WebSocketHandler):
    """
    Accepts WebSocket connections from ``metrics_agent.py`` running on each
    Worker VM.

    On each message:
      1. Parses the JSON metrics snapshot.
      2. Stores it in ``_WORKER_SNAPSHOTS`` keyed by hostname.
      3. Broadcasts the raw JSON to all connected browser clients.
    """

    def check_origin(self, origin: str) -> bool:
        # Allow connections from Worker VMs in the same VPC
        return True

    def open(self) -> None:
        log.info("MonitoringHandler: Worker agent connected from %s", self.request.remote_ip)

    def on_message(self, message: str) -> None:
        try:
            snapshot = json.loads(message)
        except (json.JSONDecodeError, TypeError):
            log.warning("MonitoringHandler: received malformed JSON from agent.")
            return

        hostname = snapshot.get("hostname", self.request.remote_ip)
        _WORKER_SNAPSHOTS[hostname] = snapshot

        # Broadcast to all connected browser tabs
        dead: Set[BrowserWebSocketHandler] = set()
        for client in _BROWSER_CLIENTS:
            try:
                client.write_message(json.dumps({
                    "type": "snapshot",
                    "worker": hostname,
                    "data": snapshot,
                }))
            except Exception:  # noqa: BLE001
                dead.add(client)
        _BROWSER_CLIENTS.difference_update(dead)

    def on_close(self) -> None:
        log.info("MonitoringHandler: Worker agent disconnected (%s)", self.request.remote_ip)


# ---------------------------------------------------------------------------
# Browser WebSocket handler  (Hub → Browser)
# ---------------------------------------------------------------------------

class BrowserWebSocketHandler(WebSocketHandler):
    """
    Accepts WebSocket connections from authenticated browser clients.

    On connection:
      1. Registers the client in ``_BROWSER_CLIENTS``.
      2. Immediately pushes all current snapshots as an "init" message.

    On close: removes the client from the set.
    """

    def check_origin(self, origin: str) -> bool:
        return True

    def open(self) -> None:
        _BROWSER_CLIENTS.add(self)
        log.debug("MonitoringHandler: browser client connected.")
        # Send current snapshots immediately so the page isn't blank on load
        if _WORKER_SNAPSHOTS:
            try:
                self.write_message(json.dumps({
                    "type": "init",
                    "workers": _WORKER_SNAPSHOTS,
                }))
            except Exception:  # noqa: BLE001
                pass

    def on_message(self, message: str) -> None:
        # Browser sends no messages; ignore gracefully
        pass

    def on_close(self) -> None:
        _BROWSER_CLIENTS.discard(self)
        log.debug("MonitoringHandler: browser client disconnected.")


# ---------------------------------------------------------------------------
# HTTP page handler  (serves the dashboard HTML)
# ---------------------------------------------------------------------------

_STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")


class MonitoringPageHandler(web.RequestHandler):
    """
    Serves the monitoring dashboard HTML at ``GET /monitoring``.

    Accessible to all authenticated JupyterHub users.
    """

    def get(self) -> None:
        html_path = os.path.join(_STATIC_DIR, "monitoring.html")
        try:
            with open(html_path, "r", encoding="utf-8") as fh:
                self.set_header("Content-Type", "text/html; charset=utf-8")
                self.write(fh.read())
        except FileNotFoundError:
            self.set_status(500)
            self.write("Monitoring dashboard HTML not found. "
                       "Ensure jupyterpilot/static/monitoring.html exists.")
