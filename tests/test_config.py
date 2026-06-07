import pytest
import sys
import os
import json
from unittest.mock import MagicMock

# Add root folder to sys.path so we can import jupyterhub_config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Import builtins config_mock from conftest/builtins
import builtins
config_mock = builtins.get_config()

# We need to make sure hub_settings.json exists or is mocked during import of jupyterhub_config.
# Since jupyterhub_config.py reads from hub_settings.json, let's mock open specifically for it or
# verify that hub_settings.json is parsed successfully.
# Let's see: the repository already has a hub_settings.json with dummy values.
# To prevent tests from failing if hub_settings.json changes or is missing, we patch builtins.open during import.
dummy_hub_settings = {
    "hub_ip": "127.0.0.1",
    "hub_port": 8000,
    "hub_bind_url": "http://127.0.0.1:8081",
    "proxy_api_url": "http://127.0.0.1:5432",
    "hub_api_url": "http://127.0.0.1:8081/hub/api",
    "hosted_domain": "test-team.com",
    "admin_users": ["admin_user"],
    "mapping_file": "user_mapping.json"
}

# Simple manual patch of builtins.open for import
orig_open = builtins.open
def custom_open(file, *args, **kwargs):
    if "hub_settings.json" in str(file):
        from io import StringIO
        return StringIO(json.dumps(dummy_hub_settings))
    return orig_open(file, *args, **kwargs)

builtins.open = custom_open
try:
    import jupyterhub_config
    from jupyterhub_config import BlockOtherUsersHandler
finally:
    builtins.open = orig_open

def test_jupyterhub_config_loaded():
    # Verify values set on config mock during import
    assert config_mock.JupyterHub.ip == "127.0.0.1"
    assert config_mock.JupyterHub.port == 8000
    assert config_mock.GoogleOAuthenticator.hosted_domain == "test-team.com"
    assert config_mock.Authenticator.admin_users == {"admin_user"}
    assert config_mock.JupyterHub.admin_access is False
    assert len(config_mock.JupyterHub.extra_handlers) > 0

@pytest.mark.anyio
async def test_block_handler_no_user():
    handler = BlockOtherUsersHandler()
    handler.current_user = None
    
    await handler.prepare()
    
    assert handler.redirect_url == "/hub/login"
    assert handler.status_code is None
    assert handler.finished_content is None

@pytest.mark.anyio
async def test_block_handler_allow_self():
    handler = BlockOtherUsersHandler()
    
    user_mock = MagicMock()
    user_mock.name = "alice"
    handler.current_user = user_mock
    handler.request.path = "/user/alice/lab"
    
    await handler.prepare()
    
    assert handler.redirect_url is None
    assert handler.status_code is None
    assert handler.finished_content is None

@pytest.mark.anyio
async def test_block_handler_deny_other_user():
    handler = BlockOtherUsersHandler()
    
    user_mock = MagicMock()
    user_mock.name = "alice"
    handler.current_user = user_mock
    handler.request.path = "/user/bob/lab"
    
    await handler.prepare()
    
    assert handler.redirect_url is None
    assert handler.status_code == 403
    assert "Access denied" in handler.finished_content

@pytest.mark.anyio
async def test_block_handler_invalid_path():
    handler = BlockOtherUsersHandler()
    
    user_mock = MagicMock()
    user_mock.name = "alice"
    handler.current_user = user_mock
    handler.request.path = "/user/"
    
    await handler.prepare()
    
    # Since target_user resolves to "" which is not "alice", it should deny access (403)
    assert handler.redirect_url is None
    assert handler.status_code == 403
    assert "Access denied" in handler.finished_content
