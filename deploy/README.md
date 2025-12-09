# EC2 Quick Demo Deployment

Simple deployment guide for running the FastAPI app on AWS EC2.

## Prerequisites

- AWS Account
- EC2 instance (recommended: `t3.medium` or larger)
- Security Group with ports: 22 (SSH), 8000 (API), 5433, 6379, 6333, 9000 open

## Quick Start

### 1. Launch EC2 Instance

**Recommended specs:**
- AMI: Amazon Linux 2023 or Ubuntu 22.04
- Instance type: `t3.medium` (2 vCPU, 4GB RAM) minimum
- Storage: 30GB+ SSD
- Security Group: Open ports 22, 8000

### 2. Connect and Run Setup

```bash
# SSH into your instance
ssh -i your-key.pem ec2-user@your-ec2-ip

# Download and run setup script
curl -O https://raw.githubusercontent.com/YOUR_REPO/main/deploy/ec2-setup.sh
chmod +x ec2-setup.sh
./ec2-setup.sh
```

### 3. Configure Environment

```bash
cd ~/BEFinalProject
nano .env  # Edit your environment variables
```

Key variables to set:
```env
# API Keys (required)
OPENAI_API_KEY=your-key
GOOGLE_API_KEY=your-key

# MinIO (local S3)
MINIO_ACCESS_KEY=minioadmin
MINIO_SECRET_KEY=minioadmin123

# Other configs...
```

### 4. Start the Application

**Option A: Manual (for debugging)**
```bash
cd ~/BEFinalProject
source venv/bin/activate
python -m src.main
```

**Option B: Background process**
```bash
cd ~/BEFinalProject
source venv/bin/activate
nohup python -m src.main > app.log 2>&1 &
```

**Option C: Systemd service (recommended)**
```bash
# Copy service file
sudo cp deploy/fastapi.service /etc/systemd/system/

# Edit if using Ubuntu (change ec2-user to ubuntu)
sudo nano /etc/systemd/system/fastapi.service

# Enable and start
sudo systemctl daemon-reload
sudo systemctl enable fastapi
sudo systemctl start fastapi

# Check status
sudo systemctl status fastapi

# View logs
sudo journalctl -u fastapi -f
```

### 5. Access Your App

```
http://your-ec2-public-ip:8000
http://your-ec2-public-ip:8000/docs  # Swagger UI
```

## Useful Commands

```bash
# Check Docker containers
cd ~/BEFinalProject/docker
docker-compose ps
docker-compose logs -f

# Restart all services
docker-compose restart

# Stop everything
docker-compose down

# View FastAPI logs
tail -f ~/BEFinalProject/app.log
# or
sudo journalctl -u fastapi -f
```

## Security Group Rules

| Type  | Port  | Source    | Description        |
|-------|-------|-----------|-------------------|
| SSH   | 22    | Your IP   | SSH access        |
| HTTP  | 8000  | 0.0.0.0/0 | FastAPI app       |
| HTTP  | 9001  | Your IP   | MinIO Console     |

## Troubleshooting

**Docker permission denied:**
```bash
sudo usermod -aG docker $USER
# Log out and log back in
```

**Port already in use:**
```bash
sudo lsof -i :8000
sudo kill -9 <PID>
```

**Check service health:**
```bash
docker-compose ps
curl http://localhost:8000/health
```

