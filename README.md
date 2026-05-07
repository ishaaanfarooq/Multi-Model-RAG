# Multi-Model RAG System 🚀
![Status](https://img.shields.io/badge/Status-Maintained-brightgreen)

A sophisticated, cloud-ready Retrieval-Augmented Generation (RAG) system designed for deep reasoning and high reliability. This system utilizes a multi-model architecture where specialized agents collaborate to provide accurate, verified, and context-aware responses.

![MultiModelRAG UI](frontend/public/next.svg) <!-- Replace with actual screenshot if available -->

## 🌟 Key Features

- **Autonomous Agentic Router**: Dynamically routes queries between Live Web Search, Local Knowledge Base (FAISS), and Direct Conversational Chat. Features a robust multi-source fallback (DuckDuckGo + Wikipedia + Google News) for uninterrupted search capabilities.
- **Data Visualizer Agent**: Automatically detects numerical/tabular data across all search branches and uses Pandas & Matplotlib to generate and return clean chart visualizations inline.
- **Master LLM Orchestrator**: Coordinates an advanced multi-agent pipeline:
  1. **Query Rewriting**: Contextualizes conversational history for precise retrieval.
  2. **Retrieval**: FAISS-powered vector search across ingested documents.
  3. **Reranking**: Cross-encoding results to filter for the highest relevance.
  4. **Generation**: Synthesis of the final answer using Llama 3.2 via Ollama, enhanced by structured paragraph prompting.
  5. **Verification & Visualization (Parallelized)**: Asynchronously executes hallucination detection and data visualization to minimize system latency.
  6. **Self-Healing Loop (OpenHive Inspired)**: Hallucination detection actively fact-checks answers and forces LLM regeneration upon failure.
- **Persistent Notebook Memory**: Saves chat history and detailed analysis, allowing users to revisit and seamlessly resume complex sessions.
- **Real-time Transparency**: Streams status updates to the frontend via Server-Sent Events (SSE) with distinct UI elements for verification warnings.
- **Multi-Source Ingestion**:
  - **PDF/Text Upload**: Ingest and index local documents.
  - **Web Crawler**: Deep-crawl entire websites to build a custom knowledge base.

## 🏗️ Core Architecture Flow

1.  **Ingestion Phase**: Documents or URLs are processed, chunked, and embedded using `sentence-transformers`.
2.  **Vector Storage**: Embeddings are stored in a **FAISS** index for ultra-fast retrieval.
3.  **Query Handling**: The **Agentic Router** analyzes the user intent and selects the best tool (Search, RAG, or Chat).
4.  **Reasoning Loop**: The **Orchestrator** generates a response, while parallel agents handle verification and data visualization.
5.  **Self-Correction**: If the **Hallucination Detector** finds inaccuracies, the system automatically regenerates the response.

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

## 🐳 Docker Deployment

The system is fully containerized. To run the entire stack (Frontend, Backend, Ollama) using Docker:

1.  **Start Services**:
    ```bash
    docker-compose up --build
    ```
2.  **Pull Models**:
    Once the containers are running, you may need to pull the Llama model into the Ollama container:
    ```bash
    docker exec -it multimodelrag-ollama-1 ollama pull llama3.2
    ```

## 📁 Repository Structure

- `backend/`: FastAPI server, orchestrator logic, and RAG components.
- `frontend/`: Next.js application with real-time pipeline visualizer.
- `deployment/`: AWS architecture diagrams and deployment notes.

## 📝 License

Distributed under the MIT License.
