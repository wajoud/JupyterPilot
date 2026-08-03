#!/usr/bin/env bash
# install_worker.sh - Automates the Worker VM setup for JupyterPilot
set -e

echo "🚀 JupyterPilot Worker VM Setup"
echo "────────────────────────────────────"

# Ensure script is run with sudo
if [ "$EUID" -ne 0 ]; then
  echo "❌ Please run this script with sudo: sudo bash install_worker.sh"
  exit 1
fi

echo "📦 1. Installing OS dependencies..."
apt update -y
apt install -y python3-pip net-tools psmisc

echo "📥 2. Cloning JupyterPilot repository..."
if [ -d "/opt/jupyterpilot" ]; then
    echo "ℹ️  /opt/jupyterpilot already exists. Updating..."
    cd /opt/jupyterpilot && git pull && cd -
else
    git clone https://github.com/wajoud/JupyterPilot.git /opt/jupyterpilot
fi

# Ask for username — MUST match the JupyterHub login username exactly
read -p "Enter the JupyterHub username to isolate (must match your Hub login, e.g. wajoud): " JUPYTER_USER

if [ -z "$JUPYTER_USER" ]; then
    echo "❌ Username cannot be empty. Setup aborted."
    exit 1
fi

echo "👤 3. Creating isolated OS user: $JUPYTER_USER..."
if id "$JUPYTER_USER" &>/dev/null; then
    echo "ℹ️  User $JUPYTER_USER already exists."
else
    adduser --disabled-password --gecos "" "$JUPYTER_USER"
fi

echo "🔑 4. Configuring SSH access..."
mkdir -p /home/$JUPYTER_USER/.ssh
read -p "Paste the public SSH key from the Hub setup step: " HUB_PUB_KEY

if [ -z "$HUB_PUB_KEY" ]; then
    echo "❌ SSH key cannot be empty. Setup aborted."
    exit 1
fi

echo "$HUB_PUB_KEY" > /home/$JUPYTER_USER/.ssh/authorized_keys
chown -R $JUPYTER_USER:$JUPYTER_USER /home/$JUPYTER_USER/.ssh
chmod 600 /home/$JUPYTER_USER/.ssh/authorized_keys

echo "🛡️ 5. Enabling loginctl lingering (prevents cgroup auto-kill)..."
loginctl enable-linger "$JUPYTER_USER"

echo "🐍 6. Installing Jupyter dependencies for $JUPYTER_USER..."
sudo -u "$JUPYTER_USER" mkdir -p /home/$JUPYTER_USER/notebook
sudo -u "$JUPYTER_USER" pip3 install jupyterhub notebook psutil websockets --break-system-packages
pip3 install psutil websockets --break-system-packages # Install globally for the metrics agent

echo "🤖 6b. Installing JupyterPilot AI extension for $JUPYTER_USER..."
sudo -u "$JUPYTER_USER" pip3 install /opt/jupyterpilot --break-system-packages

echo "🔌 7. Setting up Port Allocation script..."
cat > /home/$JUPYTER_USER/get_port.py << 'EOF'
import socket
s = socket.socket()
s.bind(('', 0))
port = s.getsockname()[1]
s.close()
print(port)
EOF
chown $JUPYTER_USER:$JUPYTER_USER /home/$JUPYTER_USER/get_port.py

echo "📊 8. Configuring the Metrics Agent systemd service..."
read -p "Enter the Hub's Private IP (to connect the agent to): " HUB_IP

cat > /etc/systemd/system/jupyterpilot-metrics.service << EOF
[Unit]
Description=JupyterPilot Metrics Agent
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/jupyterpilot/jupyterpilot/metrics_agent.py --hub ws://$HUB_IP:8000/monitoring/ws
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable jupyterpilot-metrics
systemctl restart jupyterpilot-metrics

echo ""
echo "🎉 Worker Setup Complete!"
echo "────────────────────────────────────"
echo "Isolated user '$JUPYTER_USER' is ready on this Worker VM."
echo "The metrics agent is running in the background. Check logs with:"
echo "sudo journalctl -u jupyterpilot-metrics -f"
