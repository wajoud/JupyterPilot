# ☁️ AWS EC2 Deployment Guide

This guide walks through the exact steps to deploy JupyterPilot across two EC2 instances (a Hub node and a Worker node) for testing the SSH Teleport Spawner architecture.

## 🏗️ 1. AWS Infrastructure Setup

### Instance Types
- **Recommended**: `t4g.small` (2 vCPU, 2 GiB Memory)
- **Architecture**: 64-bit Arm (Graviton)
- **OS**: Ubuntu 26.04 LTS
- **Storage**: 15 GiB `gp3` per instance (stays within the 30 GB AWS Free Tier limit).

### Security Groups
1. **EC2 #1 (The Hub)**: 
   - Allow `SSH (Port 22)` from Anywhere.
   - Allow `Custom TCP (Port 8000)` from Anywhere (this is the JupyterHub web UI).
   - Allow `Custom TCP (Port 8081)` from the **Worker's Private IP** (Allows the Worker to authenticate with the Hub API on startup).
2. **EC2 #2 (The Worker)**: 
   - Allow `All Traffic` from the **Hub's Private IP** (Allows the Hub to SSH in and proxy to random high ports).

---

## 🚀 2. EC2 #1 (Hub) Setup

SSH into your Hub instance and run the following commands. 

*(Note: Ubuntu 26.04 enforces PEP 668, so we use `--break-system-packages` to install globally on this dedicated VM).*

```bash
# 1. Install OS dependencies & Node.js (for the proxy)
sudo apt update
sudo apt install -y python3-pip sqlite3 nodejs npm
sudo npm install -g configurable-http-proxy

# 2. Install Python dependencies
pip install jupyterhub oauthenticator paramiko --break-system-packages

# 3. Clone JupyterPilot & take ownership of the directory
sudo git clone https://github.com/wajoud/JupyterPilot.git /opt/jupyterpilot
sudo chown -R $USER:$USER /opt/jupyterpilot

# 4. Setup the database directory
sudo mkdir -p /var/lib/jupyterhub
sudo chown $USER:$USER /var/lib/jupyterhub

# 5. Generate an SSH key for the spawner to use
mkdir -p /opt/jupyterpilot/keys
ssh-keygen -t ed25519 -f /opt/jupyterpilot/keys/worker -N ""

# Print the public key so you can copy it to the Worker
cat /opt/jupyterpilot/keys/worker.pub
```

**⚠️ Important:** Copy the output of the `cat` command. You will need it in the next step.

---

## 🛠️ 3. EC2 #2 (Worker) Setup

SSH into your Worker instance in a new terminal tab and run:

```bash
# 1. Install OS dependencies
sudo apt update
sudo apt install -y python3-pip net-tools psmisc

# 2. True Isolation: Create the OS-level user (e.g., test-admin)
sudo adduser --disabled-password --gecos "" test-admin

# 3. Setup SSH Access from the Hub for this user
sudo mkdir -p /home/test-admin/.ssh
# REPLACE <PASTE_KEY_HERE> with the public key you copied from the Hub!
echo "<PASTE_KEY_HERE>" | sudo tee /home/test-admin/.ssh/authorized_keys
sudo chown -R test-admin:test-admin /home/test-admin/.ssh
sudo chmod 600 /home/test-admin/.ssh/authorized_keys

# 4. Install Jupyter & Create the notebook directory specifically for test-admin
sudo -u test-admin mkdir -p /home/test-admin/notebook
sudo -u test-admin pip3 install jupyterhub notebook --break-system-packages

# 5. Create the port allocation script
cat > get_port.py << 'EOF'
import socket
s = socket.socket()
s.bind(('', 0))
port = s.getsockname()[1]
s.close()
print(port)
EOF
sudo mv get_port.py /home/test-admin/
sudo chown test-admin:test-admin /home/test-admin/get_port.py
```

**⚠️ Important:** Note the Private IP address of this Worker instance (e.g., `172.31.x.x`). You need it for the next step.

---

## ⚙️ 4. Final Configuration (Back on the Hub)

Return to your SSH session on the **Hub (EC2 #1)**.

### A. Update the Mappings
Create the mapping file to point `team_alpha` to your new Worker VM. 
*Replace `172.31.x.x` with the Worker's Private IP.*

```bash
cat > /opt/jupyterpilot/user_mapping.json << 'EOF'
{
  "team_alpha": {
    "server_ip": "172.31.x.x",
    "server_ssh_key": "/opt/jupyterpilot/keys/worker"
  }
}
EOF
```

### B. Update Hub Settings
Create the settings file. 
*Replace `172.31.y.y` with the Hub's Private IP in all 3 places.*

```bash
cat > /opt/jupyterpilot/hub_settings.json << 'EOF'
{
  "hub_ip": "172.31.y.y",
  "proxy_api_url": "http://172.31.y.y:5432",
  "hub_api_url": "http://172.31.y.y:8081/hub/api",
  "hub_bind_url": "http://172.31.y.y:8081",
  "hub_port": 8000,
  "hosted_domain": "example.com",
  "admin_users": ["test-admin"],
  "mapping_file": "/opt/jupyterpilot/user_mapping.json",
  "db_path": "/var/lib/jupyterhub/jupyterpilot_state.db"
}
EOF
```

### C. Seed the SQLite Database
Load the JSON mapping you just created into the SQLite store:

```bash
python3 /opt/jupyterpilot/jupyterpilot/seed_sqlite.py \
    --db /var/lib/jupyterhub/jupyterpilot_state.db \
    --mapping /opt/jupyterpilot/user_mapping.json
```
*(You should see `[DONE] Seeded 1 team(s)`).*

---

## 🚦 5. Start JupyterHub

You can now start the Hub! For testing without setting up Google OAuth credentials, use the dummy authenticator:

```bash
python3 -m jupyterhub -f /opt/jupyterpilot/jupyterhub_config.py \
    --JupyterHub.authenticator_class=dummy \
    --DummyAuthenticator.password=test
```

**To log in and test the Spawner:**
1. Open your browser and go to `http://<HUB-PUBLIC-IP>:8000`
2. Log in with Username: `test-admin` and Password: `test`.
3. Because `test-admin` is an admin (configured in `hub_settings.json`), click the **Admin** tab at the top.
4. Go to **Groups**, create a new group named **`team_alpha`**, and add `test-admin` to it. (The Spawner requires you to be in your mapped team before it allows you to spawn).
5. Click **Start Server**. 
6. The spawner will automatically SSH into the worker as the `test-admin` Linux user, allocate a port, and proxy your connection directly into their completely isolated `~/notebook` environment!
