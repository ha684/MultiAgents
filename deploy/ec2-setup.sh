#!/bin/bash
# EC2 Quick Demo Deployment Script
# Run this on a fresh Amazon Linux 2023 or Ubuntu EC2 instance

set -e

echo "=========================================="
echo "  FastAPI App - EC2 Quick Demo Setup"
echo "=========================================="

# Detect OS
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
fi

echo "[1/6] Installing Docker..."
if [ "$OS" = "amzn" ] || [ "$OS" = "rhel" ]; then
    # Amazon Linux 2023 / RHEL
    sudo yum update -y
    sudo yum install -y docker git
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
else
    # Ubuntu / Debian
    sudo apt-get update
    sudo apt-get install -y docker.io docker-compose git
    sudo systemctl start docker
    sudo systemctl enable docker
    sudo usermod -aG docker $USER
fi

echo "[2/6] Installing Docker Compose..."
DOCKER_COMPOSE_VERSION="v2.24.0"
sudo curl -L "https://github.com/docker/compose/releases/download/${DOCKER_COMPOSE_VERSION}/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

echo "[3/6] Installing Python 3.11..."
if [ "$OS" = "amzn" ] || [ "$OS" = "rhel" ]; then
    sudo yum install -y python3.11 python3.11-pip
else
    sudo apt-get install -y python3.11 python3.11-venv python3-pip
fi

echo "[4/6] Cloning repository..."
cd ~
if [ -d "BEFinalProject" ]; then
    cd BEFinalProject
    git pull
else
    # Replace with your actual repo URL
    git clone https://github.com/YOUR_USERNAME/BEFinalProject.git
    cd BEFinalProject
fi

echo "[5/6] Setting up environment..."
if [ ! -f ".env" ]; then
    cp .env.example .env 2>/dev/null || echo "No .env.example found, please create .env manually"
fi

# Create Python virtual environment
python3.11 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[6/6] Starting services..."
cd docker
sudo docker-compose up -d

echo ""
echo "Waiting for services to be healthy..."
sleep 30

echo ""
echo "=========================================="
echo "  Setup Complete!"
echo "=========================================="
echo ""
echo "To start the FastAPI app:"
echo "  cd ~/BEFinalProject"
echo "  source venv/bin/activate"
echo "  python -m src.main"
echo ""
echo "Or run in background with:"
echo "  nohup python -m src.main > app.log 2>&1 &"
echo ""
echo "Access your app at: http://$(curl -s http://169.254.169.254/latest/meta-data/public-ipv4):8000"
echo ""

