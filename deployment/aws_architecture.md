# AWS Cloud Deployment Architecture

This document describes how to deploy the Multi-Model RAG system on Amazon Web Services (AWS) using a modular and cost-efficient architecture.

## Overview

The system requires two types of compute profiles:
1. **CPU-Intensive Tasks:** Generating embeddings, managing FAISS vector retrieval, executing cross-encoder reranking, web crawling, and fast API handling.
2. **GPU-Intensive Tasks:** Running local LLMs (e.g., Llama3 via Ollama) for Generation and Verification modules.

We separate these workloads to optimize costs.

## Infrastructure Components

### 1. AWS EC2 (CPU Instance) - API, Retriever, Reranker, Frontend
- **Instance Type:** `c6a.xlarge` or `m5.xlarge` (compute-optimized, at least 4 vCPUs and 16GB RAM)
- **OS:** Ubuntu 22.04 LTS
- **Role:** 
  - Hosts the FastAPI Backend (except LLM inference)
  - Hosts the Next.js Frontend
  - Manages the FAISS Vector Database locally (or mapped to EFS)
  - Runs the SentenceTransformer embedding model and CrossEncoder reranker (which can run efficiently on modern CPUs)
  - Runs the website crawler
  
### 2. AWS EC2 (GPU Instance) - LLM Inference (Generator & Verifier)
- **Instance Type:** `g4dn.xlarge` or `g5.xlarge` (NVIDIA T4 or A10G GPU, 16GB+ VRAM)
- **OS:** Ubuntu 22.04 LTS (Deep Learning AMI recommended)
- **Role:**
  - Runs the `Ollama` Docker container exclusively.
  - Exposes port `11434` securely to the API instance for generating answers and verifying truthfulness.

### 3. AWS S3 (Storage)
- **Bucket Name:** `multi-model-rag-documents-bucket`
- **Role:** 
  - To implement scalable document ingestion, original PDFs and TXT files should be uploaded here. 
  - The FastAPI `ingest` route can be modified to download from S3, parse, chunk, embed, and update the FAISS index.

### 4. AWS CloudWatch
- **Role:** Monitor logs for API requests, pipeline latencies, and container health. Setup alarms for GPU memory limits or API `5XX` errors.

---

## Step-by-Step Deployment

### Prerequisites
- AWS CLI installed and configured (`aws configure`)
- An SSH key pair created in your target region
- Your AWS Account ID ready

### Step 1: Create a VPC & Security Groups

```bash
# Create a VPC (or use default VPC)
VPC_ID=$(aws ec2 describe-vpcs --filters "Name=isDefault,Values=true" --query "Vpcs[0].VpcId" --output text)
echo "Using VPC: $VPC_ID"

# Get a subnet
SUBNET_ID=$(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC_ID" --query "Subnets[0].SubnetId" --output text)

# Security Group for CPU Instance (frontend + backend API)
CPU_SG=$(aws ec2 create-security-group \
  --group-name "rag-cpu-sg" \
  --description "CPU instance - API and Frontend" \
  --vpc-id "$VPC_ID" \
  --query "GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id "$CPU_SG" --protocol tcp --port 22 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$CPU_SG" --protocol tcp --port 80 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$CPU_SG" --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$CPU_SG" --protocol tcp --port 3000 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$CPU_SG" --protocol tcp --port 8000 --cidr 0.0.0.0/0

# Security Group for GPU Instance (Ollama LLM)
GPU_SG=$(aws ec2 create-security-group \
  --group-name "rag-gpu-sg" \
  --description "GPU instance - Ollama LLM" \
  --vpc-id "$VPC_ID" \
  --query "GroupId" --output text)

aws ec2 authorize-security-group-ingress --group-id "$GPU_SG" --protocol tcp --port 22 --cidr 0.0.0.0/0
# IMPORTANT: Only allow Ollama access from CPU instance security group
aws ec2 authorize-security-group-ingress --group-id "$GPU_SG" --protocol tcp --port 11434 --source-group "$CPU_SG"

echo "CPU SG: $CPU_SG"
echo "GPU SG: $GPU_SG"
```

### Step 2: Launch GPU Instance (Ollama LLM)

```bash
# Launch GPU instance with Deep Learning AMI
GPU_INSTANCE=$(aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \
  --instance-type g4dn.xlarge \
  --key-name YOUR_KEY_PAIR_NAME \
  --security-group-ids "$GPU_SG" \
  --subnet-id "$SUBNET_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":100,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=rag-gpu-ollama}]' \
  --query "Instances[0].InstanceId" --output text)

echo "GPU Instance: $GPU_INSTANCE"

# Wait for it to be running
aws ec2 wait instance-running --instance-ids "$GPU_INSTANCE"

# Get its private IP
GPU_PRIVATE_IP=$(aws ec2 describe-instances \
  --instance-ids "$GPU_INSTANCE" \
  --query "Reservations[0].Instances[0].PrivateIpAddress" --output text)
GPU_PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$GPU_INSTANCE" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)

echo "GPU Private IP: $GPU_PRIVATE_IP"
echo "GPU Public IP: $GPU_PUBLIC_IP"
```

**SSH into GPU instance and set up Ollama:**

```bash
ssh -i YOUR_KEY.pem ubuntu@$GPU_PUBLIC_IP

# Install Docker
sudo apt-get update
sudo apt-get install -y docker.io
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu

# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg
curl -s -L https://nvidia.github.io/libnvidia-container/$distribution/libnvidia-container.list | \
  sed 's#deb https://#deb [signed-by=/usr/share/keyrings/nvidia-container-toolkit-keyring.gpg] https://#g' | \
  sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list
sudo apt-get update
sudo apt-get install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker

# Run Ollama with GPU support
docker run -d --gpus=all \
  -v ollama:/root/.ollama \
  -p 11434:11434 \
  --name ollama \
  --restart unless-stopped \
  ollama/ollama

# Pull the Llama3 model (this takes a few minutes)
docker exec -it ollama ollama pull llama3

# Verify
curl http://localhost:11434/api/tags
```

### Step 3: Launch CPU Instance (App + Frontend)

```bash
# Launch CPU instance
CPU_INSTANCE=$(aws ec2 run-instances \
  --image-id ami-0c7217cdde317cfec \
  --instance-type c6a.xlarge \
  --key-name YOUR_KEY_PAIR_NAME \
  --security-group-ids "$CPU_SG" \
  --subnet-id "$SUBNET_ID" \
  --block-device-mappings '[{"DeviceName":"/dev/sda1","Ebs":{"VolumeSize":50,"VolumeType":"gp3"}}]' \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=rag-cpu-app}]' \
  --query "Instances[0].InstanceId" --output text)

echo "CPU Instance: $CPU_INSTANCE"
aws ec2 wait instance-running --instance-ids "$CPU_INSTANCE"

CPU_PUBLIC_IP=$(aws ec2 describe-instances \
  --instance-ids "$CPU_INSTANCE" \
  --query "Reservations[0].Instances[0].PublicIpAddress" --output text)
echo "CPU Public IP: $CPU_PUBLIC_IP"
```

**SSH in and deploy the app:**

```bash
ssh -i YOUR_KEY.pem ubuntu@$CPU_PUBLIC_IP

# Install Docker & Docker Compose
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-plugin git
sudo systemctl enable docker
sudo systemctl start docker
sudo usermod -aG docker ubuntu

# Log out and back in for docker group to take effect
exit
ssh -i YOUR_KEY.pem ubuntu@$CPU_PUBLIC_IP

# Clone the project
git clone https://github.com/YOUR_USERNAME/MultiModelRAG.git
cd MultiModelRAG

# Create the .env file pointing to your GPU instance
cat > .env << EOF
OLLAMA_HOST=http://GPU_PRIVATE_IP_HERE:11434
AWS_REGION=us-east-1
CORS_ORIGINS=http://$CPU_PUBLIC_IP:3000
NEXT_PUBLIC_API_URL=http://$CPU_PUBLIC_IP:8000
EOF

# Start only backend and frontend (Ollama runs on GPU instance)
docker compose up -d backend frontend

# Check logs
docker compose logs -f
```

### Step 4: Access the Application

Open your browser and navigate to:
```
http://CPU_PUBLIC_IP:3000
```

---

## Cost Estimation

| Resource | Instance Type | On-Demand $/hr | Monthly (24/7) |
|----------|---------------|----------------|-----------------|
| CPU (App) | c6a.xlarge | ~$0.153 | ~$110 |
| GPU (LLM) | g4dn.xlarge | ~$0.526 | ~$379 |
| EBS (150GB total) | gp3 | — | ~$12 |
| **Total** | | | **~$501/month** |

> **Cost Saving Tips:**
> - Use **Spot Instances** for the GPU instance (up to 90% savings, ~$50/month)
> - Stop the GPU instance when not in use (you only pay for EBS storage)
> - Use `t3.xlarge` instead of `c6a.xlarge` for the CPU instance for dev/testing (~$0.17/hr)

---

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `Connection refused` on port 11434 | Ensure GPU instance security group allows traffic from CPU SG on port 11434 |
| Ollama model download hangs | Check GPU instance has enough disk space (100GB recommended) |
| Frontend can't reach backend | Check `NEXT_PUBLIC_API_URL` in `.env` is set to `http://CPU_PUBLIC_IP:8000` |
| CORS errors in browser | Ensure `CORS_ORIGINS` in `.env` matches the URL you're accessing frontend from |
| `CUDA out of memory` | Use `g5.xlarge` with A10G GPU (24GB VRAM) instead of `g4dn.xlarge` (16GB) |
| Slow first query | First query triggers model loading into GPU memory. Subsequent queries are faster. |

---

## Future Scalability
- Replace local FAISS with **Amazon OpenSearch Service (Serverless)** to persist embeddings safely without managing local disk state across EC2 restarts.
- Place an **Application Load Balancer (ALB)** in front of the Next.js frontend for SSL termination.
- Use **AWS Elastic Container Service (ECS)** with Fargate for auto-scaling the CPU workload.
