# Multi-Model RAG System 🚀

A sophisticated, cloud-ready Retrieval-Augmented Generation (RAG) system designed for deep reasoning and high reliability. This system utilizes a multi-model architecture where specialized agents collaborate to provide accurate, verified, and context-aware responses.

![MultiModelRAG UI](frontend/public/next.svg) <!-- Replace with actual screenshot if available -->

## 🌟 Key Features

- **Autonomous Agentic Router**: Dynamically routes queries between Live Web Search (DuckDuckGo), Local Knowledge Base (FAISS), and Direct Conversational Chat.
- **Data Visualizer Agent**: Automatically detects numerical/tabular data from the retrieved context and uses Pandas & Matplotlib to write and execute a custom Python script, returning a clean chart visualization inline with the text.
- **Master LLM Orchestrator**: Coordinates a multi-agent pipeline for every query:
  1. **Query Rewriting**: Contextualizes conversational history for precise retrieval.
  2. **Retrieval**: FAISS-powered vector search across ingested documents.
  3. **Reranking**: Cross-encoding results to filter for the highest relevance.
  4. **Generation**: Synthesis of the final answer using Llama 3.2 via Ollama.
  5. **Verification**: Hallucination detection module that fact-checks the answer against source context.
  6. **Visualization**: Invokes the Visualizer Agent to plot graphical charts if relevant data is found.
- **Real-time Transparency**: Every status update is streamed to the frontend via Server-Sent Events (SSE), showing exactly which model is doing what.
- **Multi-Source Ingestion**:
  - **PDF/Text Upload**: Ingest and index local documents.
  - **Web Crawler**: Deep-crawl entire websites to build a custom knowledge base.

## 🛠 Tech Stack

- **Backend**: FastAPI (Python), LangChain, Ollama (Llama 3.2), FAISS, BeautifulSoup, DuckDuckGo Search.
- **Frontend**: Next.js 15, React, Tailwind CSS 3, Lucide Icons.
- **AI Models**: Llama 3.2 (Local via Ollama), Sentence-Transformers (Embeddings).

## 🚀 Getting Started

### Prerequisites

- **Ollama**: [Download and install](https://ollama.com/)
- **Node.js**: v18.18+ (tested on v18.19.1)
- **Python**: 3.10+

### Setup & Run

1. **Clone the repository**:
   ```bash
   git clone https://github.com/ishaaanfarooq/Multi-Model-RAG.git
   cd Multi-Model-RAG
   ```

2. **Configure Environment**:
   ```bash
   cp .env.example .env
   ```

3. **Run the Startup Script**:
   The `start_local.sh` script automates model pulling, venv creation, and service startup.
   ```bash
   chmod +x start_local.sh
   ./start_local.sh
   ```

4. **Access the UI**:
   Open [http://localhost:3000](http://localhost:3000) in your browser.

## 📁 Repository Structure

- `backend/`: FastAPI server, orchestrator logic, and RAG components.
- `frontend/`: Next.js application with real-time pipeline visualizer.
- `deployment/`: AWS architecture diagrams and deployment notes.

## 📝 License

Distributed under the MIT License.
