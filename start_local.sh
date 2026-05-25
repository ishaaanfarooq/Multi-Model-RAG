#!/bin/bash
set -e

echo "========================================================"
echo "    Starting MultiModelRAG System Locally"
echo "    Optimized for i5 12th gen + 16GB RAM + RTX 2050"
echo "========================================================"

echo ""
echo "==> Checking for Ollama..."
if ! command -v ollama &> /dev/null; then
    echo "❌ Ollama is not installed. Please install it from https://ollama.com/download"
    exit 1
fi

echo "✅ Ollama found."
echo "==> Pulling the optimized model (llama3.2:7b-q2)..."
echo "    For your hardware (i5 + 16GB RAM + RTX 2050), Q2 is ideal."
echo "    Model size: ~3.5GB | Speed: 8-12 tokens/sec"
ollama pull llama3.2:7b-q2

echo ""
echo "==> Model pulled successfully!"
echo "    Tip: If this is slow, you can use an even lighter model:"
echo "    - phi:2.2b-q4 (1.5GB, super fast)"
echo "    - mistral:7b-q2 (3.5GB, good balance)"

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
echo "   Backend API at:   http://localhost:8000/api/health"
echo "   Ollama at:        http://localhost:11434"
echo "   Press Ctrl+C to stop both servers."
echo "========================================================"

# Wait for background processes to finish
trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit 0" INT TERM EXIT
wait
