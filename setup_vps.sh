#!/bin/bash
# Setup script for Hostinger VPS (Ubuntu/Debian)

echo "Starting Whatsapp Coach Bot Server Setup..."

# Update system
sudo apt update && sudo apt upgrade -y

# Install dependencies
sudo apt install -y python3 python3-pip python3-venv nginx certbot python3-certbot-nginx

# Navigate to app directory (assuming we are in the bot directory when running this)
APP_DIR=$(pwd)

# Create highly isolated python virtual environment
python3 -m venv venv
source venv/bin/activate

# Install requirements
pip install -r requirements.txt

# Create Systemd Service File
cat <<EOF | sudo tee /etc/systemd/system/whatsappbot.service
[Unit]
Description=WhatsApp Config Bot FastAPI Service
After=network.target

[Service]
User=$USER
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
ExecStart=$APP_DIR/venv/bin/uvicorn main:app --host 127.0.0.1 --port 8000

[Install]
WantedBy=multi-user.target
EOF

# Start and enable the bot service
sudo systemctl daemon-reload
sudo systemctl start whatsappbot.service
sudo systemctl enable whatsappbot.service

echo "✅ FastAPI App is running as a Systemd service."
echo "Setup complete. Remember to configure Nginx and Certbot next."
