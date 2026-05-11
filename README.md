# Multi-Model RAG System 🚀

[![Status](https://img.shields.io/badge/Status-Maintained-brightgreen)](https://github.com/ishaaanfarooq/Multi-Model-RAG)
[![Python](https://img.shields.io/badge/Python-51.2%25-3776ab?logo=python&logoColor=white)](https://www.python.org/)
[![TypeScript](https://img.shields.io/badge/TypeScript-44.1%25-3178c6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Last Commit](https://img.shields.io/github/last-commit/ishaaanfarooq/Multi-Model-RAG)](https://github.com/ishaaanfarooq/Multi-Model-RAG/commits)

A sophisticated, cloud-ready **Retrieval-Augmented Generation (RAG) system** designed for deep reasoning and high reliability. This multi-model architecture features specialized agents that collaborate through an intelligent orchestrator to deliver accurate, verified, and transparent responses.

## ✨ Key Features

### 🤖 **Autonomous Agentic Router**
- Dynamically routes queries between Live Web Search, Local Knowledge Base (FAISS), and Direct Chat
- Robust multi-source fallback with DuckDuckGo integration
- Intelligent source selection based on query intent

### 📊 **Data Visualizer Agent**
- Auto-detects numerical and tabular data across search results
- Generates clean visualizations using Pandas & Matplotlib
- Displays charts inline for seamless analysis

### 🧠 **Master LLM Orchestrator**
Advanced multi-agent pipeline with:
1. **Query Rewriting**: Contextualizes conversational history for precision
2. **Retrieval**: FAISS-powered vector search with semantic understanding
3. **Reranking**: Cross-encoding for maximum relevance filtering
4. **Generation**: Llama 3.2 via Ollama with structured paragraph prompting
5. **Verification & Visualization** (Parallelized): Async hallucination detection and data visualization
6. **Self-Healing Loop**: OpenHive-inspired fact-checking with automatic regeneration

### 💾 **Persistent Notebook Memory**
- Saves chat history and detailed analysis
- Seamless session resumption for complex workflows
- Full context preservation across conversations

### 🔄 **Real-Time Transparency**
- Server-Sent Events (SSE) status streaming
- Distinct UI elements for verification warnings
- Complete pipeline visibility

### 📥 **Multi-Source Ingestion**
- **PDF/Text Upload**: Index and search local documents
- **Web Crawler**: Deep-crawl entire websites for custom knowledge bases

## 🏗️ Architecture

```
┌─────────────┐      ┌──────────────┐      ┌──────────────┐
│   Input     │ ───→ │ Agentic      │ ───→ │ Orchestrator │
│   Query     │      │ Router       │      │ Pipeline     │
└─────────────┘      └──────────────┘      └──────────────┘
                            ↓                       ↓
                    ┌───────┴────────┐      ┌──────┴──────┐
                    ↓                ↓      ↓             ↓
              ┌──────────┐    ┌────────┐ ┌──────┐  ┌──────────┐
              │ Web      │    │ FAISS  │ │ Chat │  │Verify &  │
              │ Search   │    │ Vector │ │      │  │Visualize │
              └──────────┘    └────────┘ └──────┘  └──────────┘
```

## 🛠️ Tech Stack

| Category | Technology |
|----------|------------|
| **Backend** | FastAPI, LangChain, Ollama, FAISS, BeautifulSoup, DuckDuckGo |
| **Frontend** | Next.js 15, React, Tailwind CSS 3, Lucide Icons |
| **AI/ML** | Llama 3.2 (Ollama), Sentence-Transformers |
| **Infrastructure** | Docker, Docker Compose |

## 🚀 Quick Start

### Prerequisites

- **Ollama** ([Download](https://ollama.com/))
- **Node.js** v18.18+ (tested on v18.19.1)
- **Python** 3.10+
- **Docker** & **Docker Compose** (for containerized deployment)

### Local Setup

1. **Clone & Navigate**
   ```bash
   git clone https://github.com/ishaaanfarooq/Multi-Model-RAG.git
   cd Multi-Model-RAG
   ```

2. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your configuration
   ```

3. **Run Startup Script**
   ```bash
   chmod +x start_local.sh
   ./start_local.sh
   ```
   This automates model pulling, venv creation, and service startup.

4. **Access the Application**
   - Open [http://localhost:3000](http://localhost:3000) in your browser
   - Backend API: [http://localhost:8000](http://localhost:8000)

### Docker Deployment

Deploy the entire stack (Frontend, Backend, Ollama) with a single command:

```bash
docker-compose up --build
```

To pull the Llama model after containers are running:
```bash
docker exec -it multimodelrag-ollama-1 ollama pull llama3.2
```

## 📁 Repository Structure

```
Multi-Model-RAG/
├── backend/                 # FastAPI server & RAG pipeline
│   ├── app/                 # Core application logic
│   ├── services/            # Agent services & orchestration
│   └── requirements.txt
├── frontend/                # Next.js React application
│   ├── app/                 # App router structure
│   ├── components/          # React components
│   └── package.json
├── deployment/              # Cloud deployment configs
├── docker-compose.yml       # Multi-service orchestration
├── start_local.sh          # Startup automation script
└── README.md               # This file
```

## 🔧 Configuration

See `.env.example` for available environment variables:

```bash
# Ollama Settings
OLLAMA_HOST=http://localhost:11434

# Model Configuration
LLM_MODEL=llama3.2

# Backend
BACKEND_PORT=8000

# Frontend
FRONTEND_PORT=3000
```

## 📊 Performance & Monitoring

- **Streaming**: Real-time SSE updates for response generation
- **Parallelization**: Async verification & visualization tasks
- **Caching**: FAISS index persistence for instant retrieval
- **Monitoring**: Built-in pipeline visualization dashboard

## 🗺️ Roadmap

- [ ] **Multi-User Authentication**: Secure session management
- [ ] **Cloud Deployment**: AWS Terraform/CDK templates
- [ ] **Advanced Tool Integration**: Python REPL & dynamic APIs
- [ ] **Mobile Support**: Responsive mobile UI
- [ ] **Analytics Dashboard**: Usage metrics & performance insights
- [ ] **Custom Model Support**: Flexible LLM integration

## 🤝 Contributing

Contributions are welcome! Please feel free to:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## 📝 License

Distributed under the [MIT License](LICENSE). See LICENSE file for details.

## 📧 Support & Questions

- **GitHub Issues**: [Report bugs or request features](https://github.com/ishaaanfarooq/Multi-Model-RAG/issues)
- **Discussions**: [Join community discussions](https://github.com/ishaaanfarooq/Multi-Model-RAG/discussions)

---

<div align="center">

**[⬆ Back to Top](#multi-model-rag-system-)**

Made with ❤️ by [ishaaanfarooq](https://github.com/ishaaanfarooq)

</div>
