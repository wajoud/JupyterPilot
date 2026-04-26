import paramiko
import shlex
import os
import json
import asyncio
from jupyterhub.spawner import Spawner

# Load generalized settings
BASE_DIR = os.path.dirname(__file__)
SETTINGS_FILE = os.path.join(BASE_DIR, "hub_settings.json")

def load_hub_settings():
    try:
        with open(SETTINGS_FILE, "r") as f:
            return json.load(f)
    except Exception:
        return {}

hub_settings = load_hub_settings()
MAPPING_FILE = os.path.join(BASE_DIR, hub_settings.get("mapping_file", "user_mapping.json"))


class CustomSpawner(Spawner):
    _pid_file = None

    def _load_mapping(self):
        """Loads the user-server mapping from a JSON file on the fly."""
        try:
            with open(MAPPING_FILE, "r") as f:
                return json.load(f)
        except Exception as e:
            self.log.error(f"Failed to load mapping file {MAPPING_FILE}: {e}")
            raise

    def get_remote_ssh(self, server_info, ssh_user):
        ssh = paramiko.SSHClient()
        ssh.load_system_host_keys()
        ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        ssh.connect(
            server_info["server_ip"],
            username=ssh_user,
            key_filename=server_info["server_ssh_key"],
            timeout=10,
        )
        return ssh

    async def start(self):
        username = self.user.name
        # Assuming groups are managed and the first one is the team group
        user_groups = [i.name for i in self.user.groups]
        if not user_groups:
             raise Exception(f"User {username} has no groups assigned.")
        
        user_group = user_groups[0]
        mapping = self._load_mapping()

        if user_group not in mapping:
            raise Exception(f"Group {user_group} not mapped to a server in {MAPPING_FILE}.")

        server_info = mapping[user_group]
        self.ip = server_info["server_ip"]
        self._pid_file = f"/tmp/jupyterhub-{username}.pid"

        try:
            # SSH as the individual user
            ssh = self.get_remote_ssh(server_info, username)

            # 1. Get Port and check resilience
            _, stdout, _ = ssh.exec_command("python3 ~/get_port.py")
            self.port = int(stdout.readline().strip())

            # Resilience check: Verify if the port is already in use
            # We check if anything is listening on the port and try to clean up if it's a stale process
            check_cmd = f"netstat -tuln | grep ':{self.port} ' || true"
            _, stdout, _ = ssh.exec_command(check_cmd)
            if stdout.read().strip():
                self.log.warning(f"Port {self.port} on {self.ip} is already in use. Attempting to clear stale process...")
                # Attempt to kill whatever is on that port (limited to user's permissions)
                ssh.exec_command(f"fuser -k {self.port}/tcp || true")
                await asyncio.sleep(1) # Wait a bit for cleanup

            # 2. Build Env - Pointing back to the HUB'S Private IP
            env = self.get_env()
            # Use value from settings if available, otherwise fallback
            hub_api_url = hub_settings.get("hub_api_url")
            if not hub_api_url:
                raise Exception("hub_api_url not found in hub_settings.json")
            env["JUPYTERHUB_API_URL"] = hub_api_url

            exports = " ".join(
                f"{k}={shlex.quote(str(v))}"
                for k, v in env.items()
                if k.startswith("JUPYTERHUB_")
            )

            log_file = f"/tmp/jupyterhub-{username}.log"

            setup_oom_cmd = (
                "mkdir -p ~/.ipython/profile_default/startup/ && "
                "echo \"import os\ntry:\n    with open('/proc/self/oom_score_adj', 'w') as f:\n        f.write('500')\nexcept:\n    pass\" > ~/.ipython/profile_default/startup/99-admin-oom-enforcement.py"
            )
            # Execute the setup command
            _, oom_stdout, _ = ssh.exec_command(setup_oom_cmd)

            # CRITICAL: Wait for the file to finish writing to disk before moving on!
            exit_status = oom_stdout.channel.recv_exit_status()
            if exit_status != 0:
                self.log.warning(f"Failed to create OOM script for {username}")

            # 3. The Command
            cmd = (
                f"{exports} "
                f"nohup jupyterhub-singleuser "
                f"--ip=0.0.0.0 "
                f"--port={self.port} "
                f"--ServerApp.base_url={self.server.base_url} "
                f"--notebook-dir='~/notebook/' "
                f"&> {log_file} & "
                f"echo $! > {self._pid_file} && disown"
            )

            # Execute via login shell to pick up user paths
            self.log.info(f"Spawning server for {username} on {self.ip}:{self.port}")
            ssh.exec_command(f"bash -l -c {shlex.quote(cmd)}")
            ssh.close()

            # Return (IP, Port) to tell the Hub Proxy where to send traffic
            return (self.ip, self.port)

        except Exception as e:
            self.log.error(f"SSH Start failed for {username}: {e}")
            raise

    async def stop(self):
        username = self.user.name
        user_groups = [i.name for i in self.user.groups]
        if not user_groups:
            self.log.error(f"Cannot stop: User {username} has no groups.")
            return

        user_group = user_groups[0]
        mapping = self._load_mapping()
        
        if user_group not in mapping:
            self.log.error(f"Group {user_group} not in mapping during stop.")
            return

        server_info = mapping[user_group]

        try:
            ssh = self.get_remote_ssh(server_info, username)
            # Clean up with SIGTERM first, then SIGKILL if necessary
            cleanup_cmd = (
                f"if [ -f {self._pid_file} ]; then "
                f"  PID=$(cat {self._pid_file}); "
                f"  if ps -p $PID > /dev/null; then "
                f"    kill -15 $PID; "
                f"    sleep 2; "
                f"    kill -9 $PID 2>/dev/null || true; "
                f"  fi; "
                f"  rm {self._pid_file}; "
                f"fi"
            )
            self.log.info(f"Stopping server for {username} on {server_info['server_ip']}")
            ssh.exec_command(cleanup_cmd)
            ssh.close()
        except Exception as e:
            self.log.error(f"Stop failed for {username}: {e}")

    async def poll(self):
        username = self.user.name
        user_groups = [i.name for i in self.user.groups]
        if not user_groups:
            return 0 # User has no groups, assume not running

        user_group = user_groups[0]
        mapping = self._load_mapping()
        
        if user_group not in mapping:
            return 0

        server_info = mapping[user_group]

        try:
            ssh = self.get_remote_ssh(server_info, username)
            # Check if PID exists and is running
            _, stdout, _ = ssh.exec_command(
                f"ps -p $(cat {self._pid_file} 2>/dev/null) > /dev/null && echo 0 || echo 1"
            )
            status = stdout.read().decode().strip()
            ssh.close()
            return None if status == "0" else 0
        except:
            return 0

