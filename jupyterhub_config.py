# ===============================
# JupyterHub Secure Configuration
# ===============================

import os
import sys
import json
import logging
from oauthenticator.google import GoogleOAuthenticator
from jupyterhub.handlers import BaseHandler

# Load generalized settings
config_path = os.path.join(os.path.dirname(__file__), "hub_settings.json")
with open(config_path, "r") as f:
    hub_settings = json.load(f)

# Add custom spawner path dynamically
sys.path.append(os.path.dirname(__file__))
from spawner import CustomSpawner

# -------------------------------------------------
# Base Config
# -------------------------------------------------
c = get_config()

c.Application.log_level = "INFO"

# -------------------------------------------------
# Hub Network Settings
# -------------------------------------------------
c.JupyterHub.ip = hub_settings["hub_ip"]
c.JupyterHub.hub_connect_ip = hub_settings["hub_ip"]
c.JupyterHub.port = hub_settings["hub_port"]
c.JupyterHub.hub_bind_url = hub_settings["hub_bind_url"]

c.ConfigurableHTTPProxy.api_url = hub_settings["proxy_api_url"]

# -------------------------------------------------
# Authentication & Authorization
# -------------------------------------------------
c.JupyterHub.authenticator_class = GoogleOAuthenticator

c.GoogleOAuthenticator.client_id = os.getenv("CLIENT_ID")
c.GoogleOAuthenticator.client_secret = os.getenv("CLIENT_SECRET")
c.GoogleOAuthenticator.oauth_callback_url = os.getenv("OAUTH_CALLBACK_URL")

# 🔐 CRITICAL: Strictly enforce hosted domain from config
c.GoogleOAuthenticator.hosted_domain = hub_settings["hosted_domain"]

# allow_all=True at the Authenticator level allows anyone from the hosted_domain
c.Authenticator.allow_all = True

# Admin users from config
c.Authenticator.admin_users = set(hub_settings["admin_users"])

# 🔐 CRITICAL: prevent admin jumping into user servers unless explicitly needed
c.JupyterHub.admin_access = False

# One user → one server
c.JupyterHub.allow_named_servers = False

# -------------------------------------------------
# Spawner
# -------------------------------------------------
c.JupyterHub.spawner_class = CustomSpawner
c.Spawner.default_url = "/tree"

# -------------------------------------------------
# Cookie & Security Settings
# -------------------------------------------------
c.JupyterHub.cookie_options = {
    "httponly": True,
    "secure": True,
    "samesite": "Lax",
}

# -------------------------------------------------
# Extra Security: Hard Block /user/otheruser Access
# -------------------------------------------------
class BlockOtherUsersHandler(BaseHandler):
    async def prepare(self):
        user = self.current_user
        if not user:
            self.redirect("/hub/login")
            return

        path = self.request.path
        if path.startswith("/user/"):
            try:
                target_user = path.split("/")[2]
            except IndexError:
                return

            if target_user != user.name:
                self.set_status(403)
                self.finish("🚫 Access denied: You cannot access another user's server")

# Register blocker
c.JupyterHub.extra_handlers = [
    (r"/user/.*", BlockOtherUsersHandler),
]
