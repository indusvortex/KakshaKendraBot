# Windows Deployment Script for WhatsApp Coach Bot
# Run this in PowerShell as Administrator

Write-Host "Starting Windows Setup for WhatsApp Coach Bot..."

# Assuming Python is already installed and in PATH
# Create virtual environment
python -m venv venv

# Activate virtual environment and install requirements
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt

Write-Host "Dependencies installed successfully."
Write-Host "To keep the bot running 24/7 on Windows, we recommend using NSSM (Non-Sucking Service Manager) to run uvicorn as a Windows Service."
Write-Host "For HTTPS (required by WhatsApp), we recommend using Caddy, which automatically handles SSL certificates on Windows."

# Create a sample Caddyfile
$caddyfileContent = @"
yourdomain.com {
    reverse_proxy 127.0.0.1:8000
}
"@
Set-Content -Path "Caddyfile" -Value $caddyfileContent

Write-Host "Created a sample Caddyfile. Please edit it to replace yourdomain.com with your actual domain name."
