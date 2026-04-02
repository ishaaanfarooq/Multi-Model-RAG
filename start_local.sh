#!/bin/bash
set -e

echo "========================================================"
echo "    Starting MultiModelRAG System Locally"
echo "    Optimized for 16GB RAM + RTX 2050 (4GB VRAM)"
echo "========================================================"

echo ""
echo "==> Checking for Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed. Please install it from https://ollama.com/download"
    exit 1
fi

echo "✅ Ollama found."
echo "==> Pulling the lightweight model (llama3.2)..."
ollama pull llama3.2

# Ensure the faiss_index directory exists
mkdir -p backend/faiss_index

echo ""
echo "==> Setting up Python Backend..."
cd backend
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi
source venv/bin/activate
echo "Installing Python dependencies..."
pip install -r requirements.txt

echo "Starting Backend on port 8000..."
uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

echo ""
echo "==> Setting up Node.js Frontend..."
cd ../frontend
echo "Installing NPM dependencies..."
npm install

echo "Starting Frontend on port 3000..."
npm run dev &
FRONTEND_PID=$!

echo ""
echo "========================================================"
echo "✅ Both servers are starting up!"
echo "   Access the UI at: http://localhost:3000"
echo "   Backend API at:   http://localhost:8000"
echo "   Press Ctrl+C to stop both servers."
echo "========================================================"

# Wait for background processes to finish
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM EXIT
wait
