# ☁️ AWS EC2 Automated Deployment Guide

This guide walks through deploying JupyterPilot across two EC2 instances (a Hub node and a Worker node) using our automated bash setup scripts.

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

SSH into your Hub instance and run the Hub setup script. It will install all dependencies, generate an SSH key for the Spawner, and configure your JupyterHub database interactively.

```bash
# 1. Download the setup script
curl -sL https://raw.githubusercontent.com/wajoud/JupyterPilot/main/scripts/install_hub.sh -o install_hub.sh

# 2. Run the script as sudo
sudo bash install_hub.sh
```

**⚠️ Important:** At the end of the script, it will print out a public SSH key starting with `ssh-ed25519 ...`. Copy this key! You will need to paste it into the Worker setup script in the next step.

---

## 🛠️ 3. EC2 #2 (Worker) Setup

SSH into your Worker instance in a new terminal tab and run the Worker setup script. It will configure the isolated user environment, set up the monitoring agent, and apply the SSH keys.

```bash
# 1. Download the setup script
curl -sL https://raw.githubusercontent.com/wajoud/JupyterPilot/main/scripts/install_worker.sh -o install_worker.sh

# 2. Run the script as sudo
sudo bash install_worker.sh
```

When prompted, paste the SSH key that you copied from the Hub VM. The script will automatically bind it to the `test-admin` user and start the background metrics agent.

---

## 🚦 4. Start JupyterHub

Return to your SSH session on the **Hub (EC2 #1)**. You can now start the Hub!

For testing without setting up Google OAuth credentials, use the dummy authenticator:

```bash
python3 -m jupyterhub -f /opt/jupyterpilot/jupyterhub_config.py \
    --JupyterHub.authenticator_class=dummy \
    --DummyAuthenticator.password=test
```

**To log in and test the Spawner:**
1. Open your browser and go to `http://<HUB-PUBLIC-IP>:8000`
2. Log in with Username: `<your-admin-user>` (the one you provided in the Hub setup script) and Password: `test`.
3. Click the **Admin** tab at the top.
4. Go to **Groups**, create a new group named **`team_alpha`**, and add your user to it. (The Spawner requires you to be in your mapped team before it allows you to spawn).
5. Click **Start Server**. 
6. The spawner will automatically SSH into the worker, allocate a port, and proxy your connection directly into the isolated `~/notebook` environment!
